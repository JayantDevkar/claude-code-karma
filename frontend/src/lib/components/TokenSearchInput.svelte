<script lang="ts">
	import { Search, X } from 'lucide-svelte';
	import { MAX_SEARCH_TOKENS } from '$lib/search';

	interface Props {
		tokens?: string[];
		onTokensChange: (tokens: string[]) => void;
		placeholder?: string;
		class?: string;
		isLoading?: boolean;
	}

	let {
		tokens = $bindable([]),
		onTokensChange,
		placeholder = 'Search by title or prompt...',
		class: className = '',
		isLoading = false
	}: Props = $props();

	let inputValue = $state('');
	let inputRef: HTMLInputElement | undefined;
	let containerRef: HTMLDivElement | undefined;
	let tokenRefs: (HTMLElement | null)[] = $state([]);

	const isAtLimit = $derived(tokens.length >= MAX_SEARCH_TOKENS);
	const showEnterHint = $derived(inputValue.trim().length > 0 && tokens.length === 0);
	const showBackspaceHint = $derived(inputValue.trim().length === 0 && tokens.length > 0);
	const isNearLimit = $derived(tokens.length >= MAX_SEARCH_TOKENS - 1);
	const progressPercentage = $derived((tokens.length / MAX_SEARCH_TOKENS) * 100);
	let shouldPulseFocusRing = $state(false);

	// Platform detection for keyboard hint (show ⌘ on Mac, Ctrl elsewhere)
	const isMac = $derived(
		typeof navigator !== 'undefined' && /Mac|iPhone|iPod|iPad/.test(navigator.platform)
	);

	function addToken(value: string) {
		const trimmed = value.trim();
		if (!trimmed) return;
		if (tokens.includes(trimmed)) {
			// Already exists, just clear input
			inputValue = '';
			return;
		}
		if (isAtLimit) {
			inputValue = '';
			return;
		}

		const newTokens = [...tokens, trimmed];
		tokens = newTokens;
		onTokensChange(newTokens);
		inputValue = '';
	}

	function removeToken(index: number) {
		const newTokens = tokens.filter((_, i) => i !== index);
		tokens = newTokens;
		onTokensChange(newTokens);
		inputRef?.focus();
	}

	function clearAllTokens() {
		tokens = [];
		onTokensChange([]);
		inputValue = '';
		inputRef?.focus();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			addToken(inputValue);
		} else if (e.key === 'Backspace' && !inputValue && tokens.length > 0) {
			// If cursor is at start, delete last token
			if (inputRef?.selectionStart === 0 && inputRef?.selectionEnd === 0) {
				e.preventDefault();
				removeToken(tokens.length - 1);
			}
		} else if (e.key === 'ArrowLeft' && !inputValue && tokens.length > 0) {
			// Navigate to last token if cursor at start
			if (inputRef?.selectionStart === 0 && inputRef?.selectionEnd === 0) {
				e.preventDefault();
				tokenRefs[tokens.length - 1]?.focus();
			}
		} else if (e.key === 'Escape') {
			if (inputValue) {
				inputValue = '';
			} else {
				inputRef?.blur();
			}
		}
	}

	function handleTokenKeydown(e: KeyboardEvent, index: number) {
		if (e.key === 'ArrowLeft') {
			e.preventDefault();
			if (index > 0) {
				tokenRefs[index - 1]?.focus();
			}
		} else if (e.key === 'ArrowRight') {
			e.preventDefault();
			if (index < tokens.length - 1) {
				tokenRefs[index + 1]?.focus();
			} else {
				inputRef?.focus();
			}
		} else if (e.key === 'Backspace' || e.key === 'Delete') {
			e.preventDefault();
			removeToken(index);
			// Focus management: try previous, else input
			if (index > 0) {
				tokenRefs[index - 1]?.focus();
			} else {
				inputRef?.focus();
			}
		}
	}

	/**
	 * Focus the search input programmatically with pulse animation.
	 * Can be called by parent components via bind:this ref.
	 */
	export function focus() {
		shouldPulseFocusRing = true;
		inputRef?.focus();
		setTimeout(() => {
			shouldPulseFocusRing = false;
		}, 600);
	}

	function handleContainerClick(e: MouseEvent) {
		// Focus input when clicking anywhere in the container
		if (
			e.target === containerRef ||
			(e.target as Element)?.classList?.contains('tokens-area')
		) {
			inputRef?.focus();
		}
	}
</script>

<div class="token-search-wrapper {className}">
	<div
		bind:this={containerRef}
		onclick={handleContainerClick}
		class="token-search-container group"
		class:has-tokens={tokens.length > 0}
		class:at-limit={isAtLimit}
		class:pulse-focus={shouldPulseFocusRing}
	>
		<!-- Search Icon -->
		<div class="search-icon">
			<Search size={14} />
		</div>

		<!-- Tokens + Input Area -->
		<div class="tokens-area">
			{#each tokens as token, i (token)}
				<span
					bind:this={tokenRefs[i]}
					class="search-token"
					title={token}
					role="button"
					tabindex="0"
					onkeydown={(e) => handleTokenKeydown(e, i)}
					onclick={(e) => {
						e.stopPropagation();
						// Focus this token on click
						tokenRefs[i]?.focus();
					}}
				>
					<span class="token-text">{token}</span>
					<button
						type="button"
						onclick={(e) => {
							e.stopPropagation();
							removeToken(i);
						}}
						class="token-remove"
						aria-label="Remove {token}"
						tabindex="-1"
					>
						<X size={10} />
					</button>
				</span>
			{/each}

			{#if tokens.length > 0}
				<div class="token-separator"></div>
			{/if}

			<input
				bind:this={inputRef}
				type="text"
				bind:value={inputValue}
				onkeydown={handleKeydown}
				placeholder={tokens.length === 0
					? placeholder
					: isAtLimit
						? 'Max tokens reached'
						: 'Add filter...'}
				disabled={isAtLimit}
				class="token-input"
			/>
		</div>

		<!-- Token count indicator (inside container) -->
		{#if tokens.length > 0}
			<div
				class="token-count-indicator"
				class:warning={isNearLimit && !isAtLimit}
				class:danger={isAtLimit}
			>
				<div class="count-text">
					{tokens.length}/{MAX_SEARCH_TOKENS}
				</div>
				{#if tokens.length > 1}
					<div class="progress-bar">
						<div class="progress-fill" style="width: {progressPercentage}%"></div>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Right side: Clear all, loading spinner, or keyboard hint -->
		{#if tokens.length > 0}
			<button
				type="button"
				onclick={(e) => {
					e.stopPropagation();
					clearAllTokens();
				}}
				class="clear-all-btn"
				aria-label="Clear all search tokens"
			>
				<X size={14} />
			</button>
		{:else if isLoading}
			<div class="search-spinner">
				<span class="spinner"></span>
			</div>
		{:else}
			<div class="keyboard-hint">
				<kbd>{isMac ? '⌘' : 'Ctrl'}</kbd>
				<kbd>K</kbd>
			</div>
		{/if}
	</div>

	<!-- Combined Search Hints -->
	{#if showEnterHint || showBackspaceHint || tokens.length >= 2}
		<div class="search-hints">
			{#if showEnterHint}
				<span class="hint-item">
					Press <kbd>Enter</kbd> to add filter
				</span>
			{/if}

			{#if showBackspaceHint}
				<span class="hint-item">
					Press <kbd>Backspace</kbd> to remove last token
				</span>
			{/if}

			{#if tokens.length >= 2}
				<span class="hint-item">All filters must match</span>
			{/if}
		</div>
	{/if}
</div>

<style>
	.token-search-wrapper {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.token-search-container {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 38px;
		padding: 4px 12px;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 8px;
		cursor: text;
		transition: all 150ms ease;
	}

	.token-search-container:hover {
		border-color: var(--border-hover);
	}

	.token-search-container:focus-within {
		outline: none;
		box-shadow: none;
		border-color: var(--border-hover);
	}

	.token-search-container.at-limit {
		border-color: var(--warning, #f59e0b);
	}

	.search-icon {
		flex-shrink: 0;
		color: var(--text-muted);
		transition: color 150ms ease;
	}

	.token-search-container:focus-within .search-icon {
		color: var(--accent);
	}

	.tokens-area {
		flex: 1;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}

	.search-token {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		max-width: 200px;
		padding: 2px 6px 2px 10px;
		background: var(--accent-subtle);
		border-radius: 9999px;
		font-size: 12px;
		font-weight: 500;
		color: var(--accent);
		animation: token-enter 150ms ease;
		outline: none;
		border: 1px solid transparent; /* Reserve space for focus border */
	}

	.search-token:focus {
		border-color: var(--accent);
		background: var(--accent-subtle);
		box-shadow: 0 0 0 1px var(--accent);
	}

	@keyframes token-enter {
		from {
			opacity: 0;
			transform: scale(0.9);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	.token-text {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.token-remove {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 16px;
		height: 16px;
		padding: 0;
		border: none;
		background: transparent;
		border-radius: 9999px;
		color: var(--accent);
		opacity: 0.6;
		cursor: pointer;
		transition: all 150ms ease;
	}

	.token-remove:hover {
		opacity: 1;
		background: var(--accent);
		color: white;
	}

	.token-remove:focus {
		outline: none;
		opacity: 1;
	}

	.token-input {
		flex: 1;
		min-width: 100px;
		padding: 4px 0;
		border: none;
		background: transparent;
		font-size: 14px;
		color: var(--text-primary);
		outline: none;
	}

	.token-input:focus {
		outline: none !important;
		box-shadow: none !important;
		border-color: transparent !important;
	}

	.token-input::placeholder {
		color: var(--text-faint);
	}

	.token-input:disabled {
		cursor: not-allowed;
	}

	.token-input:disabled::placeholder {
		color: var(--text-faint);
		font-style: italic;
	}

	.token-separator {
		width: 1px;
		height: 20px;
		background: var(--border);
		flex-shrink: 0;
		opacity: 0;
		animation: separator-enter 150ms ease forwards;
	}

	@keyframes separator-enter {
		from {
			opacity: 0;
			transform: scaleY(0.5);
		}
		to {
			opacity: 1;
			transform: scaleY(1);
		}
	}

	.clear-all-btn {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		padding: 0;
		border: none;
		background: var(--bg-muted);
		border-radius: 6px;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 150ms ease;
	}

	.clear-all-btn:hover {
		background: var(--bg-subtle);
		color: var(--text-primary);
	}

	.clear-all-btn:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	.keyboard-hint {
		display: none;
		align-items: center;
		gap: 2px;
		color: var(--text-faint);
		opacity: 0.6;
		pointer-events: none;
		transition: opacity 150ms ease;
	}

	@media (min-width: 640px) {
		.keyboard-hint {
			display: flex;
		}
	}

	.token-search-container:focus-within .keyboard-hint {
		/* Keep hint visible on focus */
		opacity: 0.6;
	}

	.keyboard-hint kbd {
		padding: 2px 6px;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: 4px;
		font-size: 10px;
		font-family: inherit;
		font-weight: 500;
	}

	.token-count-indicator {
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 3px;
		margin-left: 8px;
		padding: 4px 10px;
		background: var(--bg-muted);
		border-radius: 6px;
		transition: all 150ms ease;
		animation: indicator-enter 150ms ease;
	}

	@keyframes indicator-enter {
		from {
			opacity: 0;
			transform: scale(0.95);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	.token-count-indicator.warning {
		background: rgba(245, 158, 11, 0.15);
	}

	.token-count-indicator.danger {
		background: rgba(239, 68, 68, 0.15);
		animation: pulse-danger 2s ease-in-out infinite;
	}

	@keyframes pulse-danger {
		0%,
		100% {
			background: rgba(239, 68, 68, 0.15);
		}
		50% {
			background: rgba(239, 68, 68, 0.25);
		}
	}

	.count-text {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-secondary);
		transition: color 150ms ease;
		white-space: nowrap;
		letter-spacing: 0.01em;
	}

	.token-count-indicator.warning .count-text {
		color: #f59e0b;
	}

	.token-count-indicator.danger .count-text {
		color: #ef4444;
	}

	.progress-bar {
		width: 44px;
		height: 3px;
		background: var(--border);
		border-radius: 9999px;
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: var(--accent);
		border-radius: 9999px;
		transition: all 150ms ease;
		transform-origin: left;
	}

	.token-count-indicator.warning .progress-fill {
		background: #f59e0b;
	}

	.token-count-indicator.danger .progress-fill {
		background: #ef4444;
	}

	.search-hints {
		font-size: 11px;
		color: var(--text-faint);
		padding-left: 12px;
		margin-top: 4px;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		row-gap: 2px;
		animation: hint-enter 200ms ease;
	}

	.hint-item {
		display: inline-flex;
		align-items: center;
	}

	.hint-item + .hint-item::before {
		content: '•';
		margin: 0 8px;
		color: var(--border-hover);
	}

	.hint-item kbd {
		padding: 1px 4px;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: 3px;
		font-size: 10px;
		font-family: inherit;
		font-weight: 500;
		margin: 0 4px;
	}

	/* Enhanced pulse animation with glow for ⌘K/Ctrl+K shortcut activation */
	@keyframes pulse-focus-ring {
		0% {
			box-shadow:
				0 0 0 2px var(--accent-subtle),
				0 0 0 0 rgba(139, 92, 246, 0);
		}
		50% {
			box-shadow:
				0 0 0 4px var(--accent-subtle),
				0 0 0 2px var(--accent),
				0 0 12px 4px rgba(139, 92, 246, 0.3);
		}
		100% {
			box-shadow:
				0 0 0 2px var(--accent-subtle),
				0 0 0 0 rgba(139, 92, 246, 0);
		}
	}

	.token-search-container.pulse-focus:focus-within {
		animation: pulse-focus-ring 600ms ease-out;
	}

	.search-spinner {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
	}

	.spinner {
		display: inline-block;
		width: 14px;
		height: 14px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 600ms linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Mobile improvements: larger touch targets and better wrapping */
	@media (max-width: 640px) {
		.token-search-container {
			min-height: 44px;
			padding: 6px 12px;
		}

		.search-token {
			min-height: 28px;
			padding: 4px 8px 4px 12px;
		}

		.token-remove {
			width: 20px;
			height: 20px;
			min-width: 20px;
			min-height: 20px;
		}

		.clear-all-btn {
			width: 32px;
			height: 32px;
			min-width: 32px;
			min-height: 32px;
		}

		.token-input {
			min-width: 120px;
			padding: 6px 0;
			font-size: 16px; /* Prevents zoom on iOS */
		}
	}
</style>
