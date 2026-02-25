/**
 * Project Tree Store
 * Manages expand/collapse state for git root groups
 * Persists state to localStorage
 */

import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const STORAGE_KEY = 'claude-dashboard:project-tree-expanded';

interface ProjectTreeState {
	expandedRoots: Set<string>;
}

function loadFromStorage(): Set<string> {
	if (!browser) {
		return new Set();
	}

	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored) {
			const parsed = JSON.parse(stored);
			return new Set(parsed.expandedRoots || []);
		}
	} catch (error) {
		console.error('Failed to load project tree state from localStorage:', error);
	}

	return new Set();
}

function saveToStorage(expandedRoots: Set<string>) {
	if (!browser) {
		return;
	}

	try {
		localStorage.setItem(
			STORAGE_KEY,
			JSON.stringify({
				expandedRoots: Array.from(expandedRoots)
			})
		);
	} catch (error) {
		console.error('Failed to save project tree state to localStorage:', error);
	}
}

function createProjectTreeStore() {
	const { subscribe, set, update } = writable<ProjectTreeState>({
		expandedRoots: loadFromStorage()
	});

	return {
		subscribe,

		/**
		 * Toggle expand/collapse state for a git root
		 */
		toggleRoot: (rootPath: string) => {
			update((state) => {
				const newExpandedRoots = new Set(state.expandedRoots);
				if (newExpandedRoots.has(rootPath)) {
					newExpandedRoots.delete(rootPath);
				} else {
					newExpandedRoots.add(rootPath);
				}
				saveToStorage(newExpandedRoots);
				return { expandedRoots: newExpandedRoots };
			});
		},

		/**
		 * Check if a git root is expanded
		 */
		isExpanded: (rootPath: string, state: ProjectTreeState): boolean => {
			return state.expandedRoots.has(rootPath);
		},

		/**
		 * Expand all git roots
		 */
		expandAll: (rootPaths: string[]) => {
			const newExpandedRoots = new Set(rootPaths);
			saveToStorage(newExpandedRoots);
			set({ expandedRoots: newExpandedRoots });
		},

		/**
		 * Collapse all git roots
		 */
		collapseAll: () => {
			const newExpandedRoots = new Set<string>();
			saveToStorage(newExpandedRoots);
			set({ expandedRoots: newExpandedRoots });
		},

		/**
		 * Check if all git roots are expanded
		 */
		isAllExpanded: (rootPaths: string[], state: ProjectTreeState): boolean => {
			if (rootPaths.length === 0) {
				return false;
			}
			return rootPaths.every((path) => state.expandedRoots.has(path));
		}
	};
}

export const projectTreeStore = createProjectTreeStore();
