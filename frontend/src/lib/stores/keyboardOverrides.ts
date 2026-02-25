/**
 * Keyboard Override Registry
 * Allows pages to register route-specific overrides for global keyboard shortcuts.
 * When a page mounts, it can register a CTRL+K override; when it unmounts, it unregisters.
 */
import { writable, get } from 'svelte/store';

type KeyboardOverride = () => void;

interface KeyboardOverrideState {
	ctrlK: KeyboardOverride | null;
}

function createKeyboardOverrideStore() {
	const { subscribe, set, update } = writable<KeyboardOverrideState>({
		ctrlK: null
	});

	return {
		subscribe,

		/**
		 * Register a CTRL+K override. Returns an unregister function.
		 * Call the returned function in onDestroy to clean up.
		 */
		registerCtrlK(handler: KeyboardOverride): () => void {
			update((state) => ({ ...state, ctrlK: handler }));
			return () => {
				update((state) => ({ ...state, ctrlK: null }));
			};
		},

		/**
		 * Get the current CTRL+K override, or null if none is registered.
		 */
		getCtrlKOverride(): KeyboardOverride | null {
			return get({ subscribe }).ctrlK;
		}
	};
}

export const keyboardOverrides = createKeyboardOverrideStore();
