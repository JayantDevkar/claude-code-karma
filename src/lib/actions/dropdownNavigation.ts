/**
 * Dropdown Keyboard Navigation Action
 * Enables ARIA-compliant keyboard navigation for dropdown menus
 */

export interface DropdownNavigationOptions {
	/** Selector for dropdown options (default: '[role="option"]') */
	optionSelector?: string;
	/** Callback when an option is selected via Enter/Space */
	onSelect?: (element: HTMLElement, index: number) => void;
	/** Callback when dropdown should close (Escape/Tab) */
	onClose?: () => void;
	/** Whether to focus first option on mount (default: true) */
	focusOnMount?: boolean;
}

/**
 * Svelte action for dropdown keyboard navigation
 * Attach to a dropdown container with role="listbox"
 */
export function dropdownNavigation(node: HTMLElement, options: DropdownNavigationOptions = {}) {
	let currentOptions = { ...options };
	const getOptionSelector = () => currentOptions.optionSelector || '[role="option"]';

	let selectedIndex = -1;

	function getOptions(): HTMLElement[] {
		return Array.from(node.querySelectorAll<HTMLElement>(getOptionSelector()));
	}

	function updateSelection(options: HTMLElement[], newIndex: number) {
		// Remove previous selection styling
		options.forEach((option, i) => {
			option.setAttribute('data-highlighted', 'false');
			if (i === newIndex) {
				option.setAttribute('data-highlighted', 'true');
				option.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
			}
		});
		selectedIndex = newIndex;
	}

	function handleKeydown(e: KeyboardEvent) {
		const options = getOptions();
		if (options.length === 0) return;

		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				e.stopPropagation();
				if (selectedIndex < options.length - 1) {
					updateSelection(options, selectedIndex + 1);
				} else {
					updateSelection(options, 0); // Wrap to first
				}
				break;

			case 'ArrowUp':
				e.preventDefault();
				e.stopPropagation();
				if (selectedIndex > 0) {
					updateSelection(options, selectedIndex - 1);
				} else {
					updateSelection(options, options.length - 1); // Wrap to last
				}
				break;

			case 'Home':
				e.preventDefault();
				e.stopPropagation();
				updateSelection(options, 0);
				break;

			case 'End':
				e.preventDefault();
				e.stopPropagation();
				updateSelection(options, options.length - 1);
				break;

			case 'Enter':
			case ' ':
				e.preventDefault();
				e.stopPropagation();
				if (selectedIndex >= 0 && selectedIndex < options.length) {
					const selectedOption = options[selectedIndex];
					if (currentOptions.onSelect) {
						currentOptions.onSelect(selectedOption, selectedIndex);
					} else {
						selectedOption.click();
					}
				}
				break;

			case 'Escape':
				e.preventDefault();
				e.stopPropagation();
				currentOptions.onClose?.();
				break;

			case 'Tab':
				// Close on tab but don't prevent default (allow focus to move)
				currentOptions.onClose?.();
				break;
		}
	}

	// Find initially selected option (one with bg-[var(--bg-subtle)] or aria-selected)
	function findInitialSelection(): number {
		const options = getOptions();
		for (let i = 0; i < options.length; i++) {
			const option = options[i];
			if (
				option.getAttribute('aria-selected') === 'true' ||
				option.classList.contains('bg-[var(--bg-subtle)]')
			) {
				return i;
			}
		}
		return 0; // Default to first option
	}

	// Initialize
	node.addEventListener('keydown', handleKeydown);

	// Focus management on mount
	if (currentOptions.focusOnMount !== false) {
		const options = getOptions();
		if (options.length > 0) {
			selectedIndex = findInitialSelection();
			updateSelection(options, selectedIndex);
			// Focus the container for keyboard events
			node.setAttribute('tabindex', '-1');
			node.focus();
		}
	}

	return {
		update(newOptions: DropdownNavigationOptions) {
			currentOptions = { ...currentOptions, ...newOptions };
		},
		destroy() {
			node.removeEventListener('keydown', handleKeydown);
			// Clean up highlight attribute
			const options = getOptions();
			options.forEach((option) => option.removeAttribute('data-highlighted'));
		}
	};
}
