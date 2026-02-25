<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import KeyIndicator from '$lib/components/ui/KeyIndicator.svelte';
	import { onMount } from 'svelte';
	import { Command, Navigation, Keyboard } from 'lucide-svelte';

	interface Props {
		open?: boolean;
		onOpenChange?: (open: boolean) => void;
	}

	let { open = $bindable(false), onOpenChange }: Props = $props();

	// Detect OS for shortcut display
	let isMac = $state(false);
	onMount(() => {
		isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
	});

	// Simplified shortcuts - only the most essential ones
	const shortcuts = $derived([
		{
			category: 'Quick Actions',
			items: [
				{ keys: [isMac ? 'cmd' : 'ctrl', 'K'], description: 'Command Menu' },
				{ keys: ['K', 'S'], description: 'This Help' }
			]
		},
		{
			category: 'Navigation',
			items: [
				{ keys: ['G', 'H'], description: 'Home' },
				{ keys: ['G', 'P'], description: 'Projects' },
				{ keys: ['G', 'A'], description: 'Agents' },
				{ keys: ['G', 'S'], description: 'Skills' }
			]
		}
	]);

	function handleOpenChange(isOpen: boolean) {
		open = isOpen;
		if (onOpenChange) {
			onOpenChange(isOpen);
		}
	}
</script>

<Modal {open} onOpenChange={handleOpenChange} title="Keyboard Shortcuts" maxWidth="sm">
	<div class="shortcuts-container">
		{#each shortcuts as section, i}
			{#if i > 0}
				<div class="section-divider"></div>
			{/if}
			<div class="section">
				<h3 class="section-title">{section.category}</h3>
				<div class="shortcuts-list">
					{#each section.items as shortcut}
						<div class="shortcut-row">
							<span class="shortcut-desc">{shortcut.description}</span>
							<KeyIndicator keys={shortcut.keys} />
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>

	<!-- Tip -->
	<div class="tip">
		<span class="tip-text">Use the Command Menu for everything else</span>
	</div>
</Modal>

<style>
	.shortcuts-container {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.section-divider {
		height: 1px;
		background: var(--border);
		margin: 0.25rem 0;
	}

	.section-title {
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
		margin-bottom: 0.75rem;
	}

	.shortcuts-list {
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
	}

	.shortcut-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.75rem;
		background: var(--bg-subtle);
		border-radius: 0.5rem;
		transition: background-color 150ms ease;
	}

	.shortcut-row:hover {
		background: var(--bg-muted);
	}

	.shortcut-desc {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.tip {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border);
		text-align: center;
	}

	.tip-text {
		font-size: 0.75rem;
		color: var(--text-muted);
	}
</style>
