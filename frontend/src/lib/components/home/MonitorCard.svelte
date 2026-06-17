<script lang="ts">
	import HomeIcon from '$lib/components/home/HomeIcon.svelte';

	interface Props {
		title: string;
		description: string;
		href: string;
		icon: string;
		/** CSS color value, e.g. 'var(--nav-blue)' */
		color: string;
		/** CSS background tint, e.g. 'var(--nav-blue-subtle)' */
		tint: string;
	}

	let { title, description, href, icon, color, tint }: Props = $props();
</script>

<a {href} class="card">
	<span class="icon-wrap" style="background: {tint}; color: {color}">
		<HomeIcon name={icon} size={24} strokeWidth={1.5} />
	</span>
	<span class="text">
		<span class="name">{title}</span>
		<span class="desc">{description}</span>
	</span>
</a>

<style>
	.card {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 11px 13px;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		text-decoration: none;
		transition:
			background 120ms,
			border-color 120ms;
	}

	.card:hover {
		background: var(--bg-muted);
		border-color: var(--border-hover);
	}

	.card:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.icon-wrap {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		border-radius: 8px;
		flex-shrink: 0;
	}

	.text {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.name {
		font-size: 13px;
		font-weight: 600;
		color: var(--text-primary);
		line-height: 1.2;
	}

	.desc {
		font-size: 10.5px;
		color: var(--text-faint);
		margin-top: 1px;
	}
</style>
