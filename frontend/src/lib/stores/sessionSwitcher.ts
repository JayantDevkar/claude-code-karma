/**
 * Session Switcher Store
 * Lets sibling components (e.g. CommandFooter's button) open the Cmd+B
 * switcher HUD, mirroring the commandPalette store's open/close pattern.
 */

import { writable, get } from 'svelte/store';

interface SessionSwitcherState {
	isOpen: boolean;
}

function createSessionSwitcherStore() {
	const { subscribe, set } = writable<SessionSwitcherState>({ isOpen: false });

	return {
		subscribe,
		open: () => set({ isOpen: true }),
		close: () => set({ isOpen: false }),
		getIsOpen: () => get({ subscribe }).isOpen
	};
}

export const sessionSwitcherStore = createSessionSwitcherStore();
