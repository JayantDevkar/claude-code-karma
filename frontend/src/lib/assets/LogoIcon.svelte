<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	width={size}
	height={size}
	viewBox="0 0 128 128"
	class={className}
>
	<defs>
		<linearGradient id="logo-fg" x1="0%" y1="0%" x2="100%" y2="100%">
			<stop offset="0%" style="stop-color:#a855f7" />
			<stop offset="100%" style="stop-color:#7c3aed" />
		</linearGradient>
		<filter id="logo-glow">
			<feGaussianBlur stdDeviation="1.5" result="b" />
			<feMerge>
				<feMergeNode in="b" />
				<feMergeNode in="SourceGraphic" />
			</feMerge>
		</filter>
	</defs>
	<!-- Orbit rings -->
	<ellipse
		cx="64"
		cy="64"
		rx="58"
		ry="28"
		fill="none"
		stroke="currentColor"
		stroke-width="3"
		opacity="0.25"
		transform="rotate(-20 64 64)"
	/>
	<ellipse
		cx="64"
		cy="64"
		rx="58"
		ry="28"
		fill="none"
		stroke="currentColor"
		stroke-width="2.5"
		opacity="0.4"
		transform="rotate(15 64 64)"
	/>
	<ellipse
		cx="64"
		cy="64"
		rx="58"
		ry="28"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		opacity="0.2"
		transform="rotate(50 64 64)"
	/>
	<!-- Infinity / karma symbol -->
	<g transform="translate(64,64)" filter="url(#logo-glow)">
		<path
			d="M0,0 C-12,-16 -34,-16 -34,0 C-34,16 -12,16 0,0 C12,-16 34,-16 34,0 C34,16 12,16 0,0 Z"
			fill="none"
			stroke="url(#logo-fg)"
			stroke-width="6"
			stroke-linecap="round"
		/>
		<path
			d="M0,0 C-12,-16 -34,-16 -34,0 C-34,16 -12,16 0,0 C12,-16 34,-16 34,0 C34,16 12,16 0,0 Z"
			fill="none"
			stroke="#e9d5ff"
			stroke-width="2"
			opacity="0.35"
		/>
	</g>
	<!-- Code symbols -->
	<g fill="#c4b5fd" font-family="monospace" opacity="0.6">
		<text x="16" y="42" font-size="11" transform="rotate(-15 16 42)">&lt;/&gt;</text>
		<text x="90" y="100" font-size="10" transform="rotate(12 90 100)">&#123; &#125;</text>
	</g>
	<!-- Orbit dots -->
	<circle cx="112" cy="50" r="4.5" fill="currentColor" opacity="0.7" />
	<circle cx="16" cy="78" r="3.5" fill="currentColor" opacity="0.45" />
	<circle cx="82" cy="16" r="3" fill="currentColor" opacity="0.5" />
	<circle cx="46" cy="112" r="3" fill="currentColor" opacity="0.35" />
</svg>
