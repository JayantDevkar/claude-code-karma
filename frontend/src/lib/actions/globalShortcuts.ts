/**
 * Global Shortcuts Action
 * Handles vim-style multi-key shortcuts for navigation
 */

import { goto } from '$app/navigation';
import { commandPalette } from '$lib/stores/commandPalette';
import { isTyping } from '$lib/utils/keyboard';

export interface GlobalShortcutsOptions {
	onToggleTheme?: () => void;
	onToggleHelp?: () => void;
}

// Shortcut definitions
type ShortcutAction = () => void;

const shortcuts: Record<string, ShortcutAction> = {
	'g p': () => goto('/projects'),
	'g a': () => goto('/agents'),
	'g s': () => goto('/skills'),
	'g h': () => goto('/'),
	'/': () => {
		const searchInput = document.querySelector<HTMLInputElement>('[data-search-input]');
		if (searchInput) {
			searchInput.focus();
			searchInput.select();
		}
	}
};

// Dynamic shortcuts that need options
let dynamicShortcuts: Record<string, ShortcutAction> = {};

/**
 * Svelte action for global keyboard shortcuts with multi-key sequence support
 */
export function globalShortcuts(node: HTMLElement, options: GlobalShortcutsOptions = {}) {
	let keySequence = '';
	let sequenceTimeout: ReturnType<typeof setTimeout> | null = null;

	// Initialize dynamic shortcuts
	if (options.onToggleHelp) {
		dynamicShortcuts['k s'] = options.onToggleHelp;
	}

	function handleKeydown(e: KeyboardEvent) {
		// Don't handle if command palette is open
		if (commandPalette.getIsOpen()) {
			return;
		}

		// Don't handle if typing in an input (except for specific shortcuts)
		if (isTyping()) {
			return;
		}

		// Clear any existing timeout
		if (sequenceTimeout) {
			clearTimeout(sequenceTimeout);
			sequenceTimeout = null;
		}

		// Handle single-key shortcuts first
		if (e.key === 't' && !e.metaKey && !e.ctrlKey && !e.altKey) {
			e.preventDefault();
			if (options.onToggleTheme) {
				options.onToggleTheme();
			}
			keySequence = '';
			return;
		}

		// Build key sequence
		if (keySequence) {
			keySequence += ' ' + e.key;
		} else {
			keySequence = e.key;
		}

		// Check for exact match in static and dynamic shortcuts
		const allShortcuts = { ...shortcuts, ...dynamicShortcuts };
		const action = allShortcuts[keySequence];
		if (action) {
			e.preventDefault();
			action();
			keySequence = '';
			return;
		}

		// Check if any shortcut starts with current sequence
		const hasPrefix = Object.keys(allShortcuts).some((s) => s.startsWith(keySequence));
		if (hasPrefix) {
			// Wait for more keys
			sequenceTimeout = setTimeout(() => {
				keySequence = '';
			}, 1000);
		} else {
			// No matching shortcuts, reset
			keySequence = '';
		}
	}

	// Add event listener
	window.addEventListener('keydown', handleKeydown);

	return {
		update(newOptions: GlobalShortcutsOptions) {
			options = newOptions;
			// Update dynamic shortcuts with new options
			dynamicShortcuts = {};
			if (options.onToggleHelp) {
				dynamicShortcuts['k s'] = options.onToggleHelp;
			}
		},
		destroy() {
			window.removeEventListener('keydown', handleKeydown);
			if (sequenceTimeout) {
				clearTimeout(sequenceTimeout);
			}
		}
	};
}
