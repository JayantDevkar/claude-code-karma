<script lang="ts">
	import { Sun, Moon } from 'lucide-svelte';
	import { onMount } from 'svelte';

	type Theme = 'light' | 'dark';

	let theme = $state<Theme>('light');

	onMount(() => {
		// Get stored preference, or detect system preference
		const stored = localStorage.getItem('theme') as Theme | null;
		if (stored && (stored === 'light' || stored === 'dark')) {
			theme = stored;
			applyTheme(stored);
		} else {
			// Default to system preference on first visit
			const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
			theme = prefersDark ? 'dark' : 'light';
			applyTheme(theme);
		}
	});

	function applyTheme(newTheme: Theme) {
		document.documentElement.setAttribute('data-theme', newTheme);
		localStorage.setItem('theme', newTheme);
	}

	function toggleTheme() {
		theme = theme === 'light' ? 'dark' : 'light';
		applyTheme(theme);
	}
</script>

<button
	onclick={toggleTheme}
	class="
		p-2 rounded-lg
		text-[var(--text-muted)]
		hover:text-[var(--text-primary)]
		hover:bg-[var(--bg-muted)]
		transition-colors duration-200
		focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
	"
	title="Switch to {theme === 'light' ? 'dark' : 'light'} mode"
	aria-label="Switch to {theme === 'light' ? 'dark' : 'light'} mode"
>
	{#if theme === 'light'}
		<Sun size={16} strokeWidth={2} />
	{:else}
		<Moon size={16} strokeWidth={2} />
	{/if}
</button>
