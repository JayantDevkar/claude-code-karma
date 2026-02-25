/**
 * List Navigation Action
 * Enables vim-style j/k navigation for list components
 */

import { commandPalette } from '$lib/stores/commandPalette';
import { isTyping } from '$lib/utils/keyboard';

export interface ListNavigationOptions {
	/** Selector for list items (default: '[data-list-item]') */
	itemSelector?: string;
	/** Callback when an item is selected via Enter */
	onSelect?: (element: HTMLElement, index: number) => void;
	/** Whether to scroll item into view (default: true) */
	scrollIntoView?: boolean;
}

/**
 * Svelte action for vim-style list navigation
 * Attach to a container element that wraps list items
 */
export function listNavigation(node: HTMLElement, options: ListNavigationOptions = {}) {
	// Store options in mutable variable for proper update handling
	let currentOptions = { ...options };
	const getItemSelector = () => currentOptions.itemSelector || '[data-list-item]';
	const getScrollIntoView = () => currentOptions.scrollIntoView ?? true;

	let selectedIndex = -1;
	let lastKeyTime = 0;
	let lastKey = '';
	const SEQUENCE_TIMEOUT = 500;

	function getItems(): HTMLElement[] {
		return Array.from(node.querySelectorAll<HTMLElement>(getItemSelector()));
	}

	function updateSelection(items: HTMLElement[], newIndex: number) {
		// Remove previous selection
		items.forEach((item) => {
			item.removeAttribute('data-vim-selected');
		});

		// Set new selection
		selectedIndex = newIndex;
		if (selectedIndex >= 0 && selectedIndex < items.length) {
			const selectedItem = items[selectedIndex];
			selectedItem.setAttribute('data-vim-selected', 'true');

			// Scroll into view if needed
			if (getScrollIntoView()) {
				selectedItem.scrollIntoView({
					behavior: 'smooth',
					block: 'nearest'
				});
			}
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		// Don't handle if command palette is open
		if (commandPalette.getIsOpen()) {
			return;
		}

		// Don't handle if typing in an input
		if (isTyping()) {
			return;
		}

		const items = getItems();
		if (items.length === 0) return;

		const now = Date.now();
		const isSequence = now - lastKeyTime < 500;

		switch (e.key) {
			case 'j':
				e.preventDefault();
				if (selectedIndex < items.length - 1) {
					updateSelection(items, selectedIndex + 1);
				} else if (selectedIndex === -1) {
					updateSelection(items, 0);
				}
				break;

			case 'k':
				e.preventDefault();
				if (selectedIndex > 0) {
					updateSelection(items, selectedIndex - 1);
				} else if (selectedIndex === -1) {
					updateSelection(items, items.length - 1);
				}
				break;

			case 'Enter':
				if (selectedIndex >= 0 && selectedIndex < items.length) {
					e.preventDefault();
					const selectedItem = items[selectedIndex];

					// Trigger click or callback
					if (currentOptions.onSelect) {
						currentOptions.onSelect(selectedItem, selectedIndex);
					} else {
						// Find and click the anchor or button
						const clickable = selectedItem.querySelector('a, button') || selectedItem;
						if (clickable instanceof HTMLElement) {
							clickable.click();
						}
					}
				}
				break;

			case 'g':
				if (lastKey === 'g' && now - lastKeyTime < SEQUENCE_TIMEOUT) {
					// gg - go to first item
					e.preventDefault();
					updateSelection(items, 0);
					lastKey = '';
					lastKeyTime = 0;
				} else {
					lastKey = 'g';
					lastKeyTime = now;
				}
				return; // Don't update lastKey at the end for 'g'

			case 'G':
				// G - go to last item
				e.preventDefault();
				updateSelection(items, items.length - 1);
				break;

			case 'Escape':
				// Clear selection
				if (selectedIndex >= 0) {
					e.preventDefault();
					items.forEach((item) => item.removeAttribute('data-vim-selected'));
					selectedIndex = -1;
				}
				break;

			default:
				// Reset sequence tracking for other keys
				lastKey = '';
				lastKeyTime = 0;
		}
	}

	// Handle click to update selection
	function handleClick(e: MouseEvent) {
		const target = e.target as HTMLElement;
		const item = target.closest(getItemSelector()) as HTMLElement | null;

		if (item) {
			const items = getItems();
			const index = items.indexOf(item);
			if (index >= 0) {
				updateSelection(items, index);
			}
		}
	}

	// Add event listeners
	window.addEventListener('keydown', handleKeydown);
	node.addEventListener('click', handleClick);

	return {
		update(newOptions: ListNavigationOptions) {
			// Update mutable options reference for proper closure handling
			currentOptions = { ...currentOptions, ...newOptions };
		},
		destroy() {
			window.removeEventListener('keydown', handleKeydown);
			node.removeEventListener('click', handleClick);

			// Clean up selection attribute
			const items = getItems();
			items.forEach((item) => item.removeAttribute('data-vim-selected'));
		}
	};
}
