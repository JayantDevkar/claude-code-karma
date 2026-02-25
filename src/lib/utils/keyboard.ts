/**
 * Keyboard Utilities
 * Shared utilities for keyboard handling across the application
 */

/**
 * Check if user is currently typing in an input field
 * Used to prevent keyboard shortcuts from firing when user is entering text
 */
export function isTyping(): boolean {
	const active = document.activeElement;
	if (!active) return false;

	const tag = active.tagName.toLowerCase();
	if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
	if (active.getAttribute('contenteditable') === 'true') return true;

	// Check if inside command palette input
	if (active.hasAttribute('data-command-input')) return true;

	return false;
}
