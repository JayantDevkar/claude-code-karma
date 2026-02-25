<script lang="ts">
	import { onMount } from 'svelte';
	import { Command, Sun, Moon, Keyboard } from 'lucide-svelte';
	import { commandPalette } from '$lib/stores/commandPalette';
	import KeyIndicator from '$lib/components/ui/KeyIndicator.svelte';

	interface Props {
		onToggleHelp?: () => void;
	}

	let { onToggleHelp }: Props = $props();

	// Detect OS for shortcut display
	let isMac = $state(true);
	// Track current theme - check actual theme on mount
	let isDark = $state(false);

	onMount(() => {
		isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
		// Check current theme from DOM or localStorage
		const theme =
			document.documentElement.getAttribute('data-theme') ||
			localStorage.getItem('theme') ||
			'dark';
		isDark = theme === 'dark';
	});

	// Toggle theme function
	function toggleTheme() {
		const current = document.documentElement.getAttribute('data-theme');
		const newTheme = current === 'dark' ? 'light' : 'dark';
		document.documentElement.setAttribute('data-theme', newTheme);
		localStorage.setItem('theme', newTheme);
		isDark = newTheme === 'dark';
	}
</script>

<footer class="command-footer">
	<div class="footer-content">
		<!-- Toggle Theme -->
		<button type="button" class="command-btn" onclick={toggleTheme} title="Toggle Theme">
			{#if isDark}
				<Moon size={14} />
			{:else}
				<Sun size={14} />
			{/if}
			<span class="label">Toggle Theme</span>
			<KeyIndicator keys={['T']} class="shortcut" />
		</button>

		<!-- Keyboard Shortcuts -->
		<button
			type="button"
			class="command-btn"
			onclick={() => onToggleHelp?.()}
			title="Keyboard Shortcuts"
		>
			<Keyboard size={14} />
			<span class="label">Keyboard Shortcuts</span>
			<KeyIndicator keys={['K', 'S']} class="shortcut" />
		</button>

		<!-- Command Menu -->
		<button
			type="button"
			class="command-btn"
			onclick={() => commandPalette.open()}
			title="Command Menu"
		>
			<Command size={14} />
			<span class="label">Command Menu</span>
			<KeyIndicator keys={[isMac ? 'cmd' : 'ctrl', 'K']} class="shortcut" />
		</button>
	</div>
</footer>

<style>
	.command-footer {
		margin-top: auto;
		padding: 1.5rem 0 0.5rem;
	}

	.footer-content {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.command-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 150ms ease;
	}

	.command-btn:hover {
		color: var(--text-primary);
		background: var(--bg-muted);
		border-color: var(--border-strong);
	}

	.label {
		display: none;
	}

	/* Show labels on larger screens */
	@media (min-width: 640px) {
		.label {
			display: inline;
		}
	}

	.command-btn :global(.shortcut) {
		opacity: 0.6;
		margin-left: 0.25rem;
	}

	.command-btn:hover :global(.shortcut) {
		opacity: 1;
	}
</style>
