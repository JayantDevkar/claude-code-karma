<script lang="ts">
	interface Props {
		keys: string[];
		class?: string;
	}

	let { keys, class: className = '' }: Props = $props();

	// Format key for display
	function formatKey(key: string): string {
		const keyMap: Record<string, string> = {
			cmd: '⌘',
			ctrl: '⌃',
			alt: '⌥',
			shift: '⇧',
			enter: '↵',
			escape: 'Esc',
			esc: 'Esc',
			tab: '⇥',
			backspace: '⌫',
			delete: '⌦',
			up: '↑',
			down: '↓',
			left: '←',
			right: '→',
			space: '␣'
		};
		return keyMap[key.toLowerCase()] || key.toUpperCase();
	}
</script>

<span class="inline-flex items-center gap-0.5 {className}">
	{#each keys as key, i}
		{#if i > 0 && !['cmd', 'ctrl', 'alt', 'shift'].includes(keys[i - 1].toLowerCase())}
			<span class="text-[var(--text-faint)] text-[10px] mx-0.5">then</span>
		{/if}
		<kbd
			class="
				inline-flex items-center justify-center
				min-w-[20px] h-5
				px-1.5
				text-[11px] font-medium
				bg-[var(--bg-muted)]
				border border-[var(--border)]
				rounded-[4px]
				text-[var(--text-secondary)]
				shadow-[0_1px_0_var(--border)]
			"
		>
			{formatKey(key)}
		</kbd>
	{/each}
</span>
