/**
 * Command Palette Store
 * Simple open/close state management (matching React/cmdk pattern)
 */

import { writable, get } from 'svelte/store';

interface CommandPaletteState {
	isOpen: boolean;
}

function createCommandPaletteStore() {
	const { subscribe, set, update } = writable<CommandPaletteState>({
		isOpen: false
	});

	return {
		subscribe,

		/**
		 * Open the command palette
		 */
		open: () => set({ isOpen: true }),

		/**
		 * Close the command palette
		 */
		close: () => set({ isOpen: false }),

		/**
		 * Toggle the command palette
		 */
		toggle: () => update((state) => ({ isOpen: !state.isOpen })),

		/**
		 * Get current open state
		 */
		getIsOpen: () => get({ subscribe }).isOpen
	};
}

export const commandPalette = createCommandPaletteStore();
