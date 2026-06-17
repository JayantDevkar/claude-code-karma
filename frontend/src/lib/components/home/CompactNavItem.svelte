<script lang="ts">
	import HomeIcon from '$lib/components/home/HomeIcon.svelte';

	interface Props {
		title: string;
		href: string;
		icon: string;
		/** CSS color value, e.g. 'var(--nav-purple)' */
		color: string;
		/** CSS background tint, e.g. 'var(--nav-purple-subtle)' */
		tint: string;
	}

	let { title, href, icon, color, tint }: Props = $props();
</script>

<a {href} class="item">
	<span class="icon-wrap" style="background: {tint}; color: {color}">
		<HomeIcon name={icon} size={22} strokeWidth={1.5} />
	</span>
	<span class="name">{title}</span>
</a>

<style>
	.item {
		display: flex;
		align-items: center;
		gap: 9px;
		padding: 10px 12px;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 7px;
		text-decoration: none;
		transition:
			background 120ms,
			border-color 120ms;
	}

	.item:hover {
		background: var(--bg-subtle);
		border-color: var(--border-hover);
	}

	.item:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.icon-wrap {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 34px;
		height: 34px;
		border-radius: 7px;
		flex-shrink: 0;
	}

	.name {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-primary);
	}
</style>
