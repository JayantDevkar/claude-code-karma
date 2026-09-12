<script lang="ts">
	import { metaFor, fillFor, shapeSpec } from './kinds';

	interface Props {
		kind: string;
		/** Bounding-box size in px. */
		size?: number;
		class?: string;
	}

	let { kind, size = 30, class: className = '' }: Props = $props();

	const meta = $derived(metaFor(kind));
	const pad = 3;
	const box = $derived(size + pad * 2);
	const spec = $derived(shapeSpec(meta.shape, box / 2, box / 2, size));
</script>

<svg
	width={box}
	height={box}
	viewBox={`0 0 ${box} ${box}`}
	class={className}
	aria-hidden="true"
	focusable="false"
>
	{#if spec.el === 'circle'}
		<circle {...spec.attrs} fill={fillFor(kind)} stroke={meta.color} stroke-width="1.5" />
	{:else if spec.el === 'rect'}
		<rect {...spec.attrs} fill={fillFor(kind)} stroke={meta.color} stroke-width="1.5" />
	{:else}
		<polygon {...spec.attrs} fill={fillFor(kind)} stroke={meta.color} stroke-width="1.5" />
	{/if}
	<text
		x={box / 2}
		y={box / 2}
		text-anchor="middle"
		dominant-baseline="central"
		font-size={meta.initial.length > 1 ? size * 0.36 : size * 0.46}
		font-weight="700"
		fill={meta.color}
	>
		{meta.initial}
	</text>
</svg>
