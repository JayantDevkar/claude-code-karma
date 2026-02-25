/**
 * Global Keyboard Action
 * Handles global keyboard shortcuts like Cmd+K for command palette
 */

import { commandPalette } from '$lib/stores/commandPalette';
import { keyboardOverrides } from '$lib/stores/keyboardOverrides';
import { isTyping } from '$lib/utils/keyboard';

export interface GlobalKeyboardOptions {
	onToggleHelp?: () => void;
}

/**
 * Svelte action for global keyboard handling
 * Attach to the root layout element
 */
export function globalKeyboard(node: HTMLElement, options: GlobalKeyboardOptions = {}) {
	function handleKeydown(e: KeyboardEvent) {
		// Cmd+K or Ctrl+K - Check for route-specific override first, then toggle command palette
		// This should work even when typing in inputs (standard pattern)
		if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
			e.preventDefault();

			// Check for page-specific override (e.g., focus search on /sessions)
			const override = keyboardOverrides.getCtrlKOverride();
			if (override) {
				// If command palette is already open, close it instead of calling override
				if (commandPalette.getIsOpen()) {
					commandPalette.close();
				} else {
					override();
				}
			} else {
				// No override registered, use default behavior
				commandPalette.toggle();
			}
			return;
		}

		// If command palette is open, don't handle other shortcuts
		if (commandPalette.getIsOpen()) {
			return;
		}

		// Don't handle shortcuts when typing in inputs (except Cmd+K above)
		if (isTyping()) {
			return;
		}

		// ? - Show keyboard help
		if (e.key === '?' && !e.metaKey && !e.ctrlKey && !e.altKey) {
			e.preventDefault();
			if (options.onToggleHelp) {
				options.onToggleHelp();
			}
			return;
		}
	}

	// Add listener to window for global capture
	window.addEventListener('keydown', handleKeydown);

	return {
		update(newOptions: GlobalKeyboardOptions) {
			options = newOptions;
		},
		destroy() {
			window.removeEventListener('keydown', handleKeydown);
		}
	};
}
