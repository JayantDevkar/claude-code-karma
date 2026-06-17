<script lang="ts">
	interface Props {
		name: string;
		size?: number;
		strokeWidth?: number;
	}

	let { name, size = 24, strokeWidth = 1.5 }: Props = $props();
</script>

{#if name === 'projects'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<circle cx="12" cy="20" r="2" />
		<circle cx="6" cy="4" r="2" />
		<circle cx="18" cy="4" r="2" />
		<line x1="12" y1="18" x2="12" y2="12" />
		<path d="M12 12 C12 9 6 9 6 6" />
		<path d="M12 12 C12 9 18 9 18 6" />
	</svg>
{:else if name === 'sessions'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<rect x="2" y="3" width="20" height="18" rx="3" />
		<line x1="2" y1="8" x2="22" y2="8" />
	</svg>
{:else if name === 'analytics'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<line x1="6" y1="4" x2="6" y2="7"/>
		<rect x="4.5" y="7" width="3" height="7" rx="0.5"/>
		<line x1="6" y1="14" x2="6" y2="17"/>
		<line x1="12" y1="6" x2="12" y2="9"/>
		<rect x="10.5" y="9" width="3" height="5" rx="0.5" fill="currentColor" fill-opacity="0.15"/>
		<line x1="12" y1="14" x2="12" y2="18"/>
		<line x1="18" y1="3" x2="18" y2="6"/>
		<rect x="16.5" y="6" width="3" height="9" rx="0.5"/>
		<line x1="18" y1="15" x2="18" y2="19"/>
		<line x1="2" y1="21" x2="22" y2="21" opacity="0.3"/>
	</svg>
{:else if name === 'agents'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<line x1="12" y1="2" x2="12" y2="5"/>
		<circle cx="12" cy="1.5" r="1.2"/>
		<rect x="4" y="5" width="16" height="13" rx="3"/>
		<circle cx="9" cy="10.5" r="2"/>
		<circle cx="15" cy="10.5" r="2"/>
		<line x1="10" y1="15" x2="14" y2="15"/>
		<path d="M4 11 C1.5 11 1.5 14 4 14"/>
		<path d="M20 11 C22.5 11 22.5 14 20 14"/>
	</svg>
{:else if name === 'skills'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<path d="M12 2 L20 6 L20 12 Q20 18 12 22 Q4 18 4 12 L4 6 Z" />
		<polyline points="8.5,12 11,14.5 15.5,9.5" />
	</svg>
{:else if name === 'tools'}
	<!-- Exact MCP (Model Context Protocol) logo paths, scaled via viewBox -->
	<svg width={size} height={size} viewBox="0 0 180 180" fill="none" stroke="currentColor" stroke-width={strokeWidth * 7.5} stroke-linecap="round">
		<path d="M18 84.8528L85.8822 16.9706C95.2548 7.59798 110.451 7.59798 119.823 16.9706C129.196 26.3431 129.196 41.5391 119.823 50.9117L68.5581 102.177"/>
		<path d="M69.2652 101.47L119.823 50.9117C129.196 41.5391 144.392 41.5391 153.765 50.9117L154.118 51.2652C163.491 60.6378 163.491 75.8338 154.118 85.2063L92.7248 146.6C89.6006 149.724 89.6006 154.789 92.7248 157.913L105.331 170.52"/>
		<path d="M102.853 33.9411L52.6482 84.1457C43.2756 93.5183 43.2756 108.714 52.6482 118.087C62.0208 127.459 77.2167 127.459 86.5893 118.087L136.794 67.8822"/>
	</svg>
{:else if name === 'commands'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<rect x="3" y="3" width="18" height="18" rx="3" />
		<polyline points="8,9 12,12 8,15" />
		<line x1="13" y1="15" x2="16" y2="15" />
	</svg>
{:else if name === 'hooks'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<circle cx="14" cy="3.5" r="1.5" />
		<line x1="14" y1="5" x2="14" y2="14" />
		<path d="M14 14 C14 21 8 21 8 14 L8 9" />
		<path d="M8 11.5 L5.5 13.5" />
	</svg>
{:else if name === 'cron'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<circle cx="12" cy="13" r="8" />
		<polyline points="12,8 12,13 15,15" />
		<path d="M20 4 A12 12 0 0 1 22 10" />
		<polyline points="17.5,3.5 20,4 19,6.5" />
	</svg>
{:else if name === 'plans'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
		<rect x="5" y="5" width="14" height="16" rx="1.5" stroke-width={strokeWidth} opacity="0.2"/>
		<rect x="3.5" y="3.5" width="14" height="16" rx="1.5" stroke-width={strokeWidth} opacity="0.5"/>
		<rect x="2" y="2" width="14" height="16" rx="1.5" stroke-width={strokeWidth}/>
		<line x1="5" y1="6.5" x2="13" y2="6.5" stroke-width={strokeWidth * 0.8} opacity="0.7"/>
		<line x1="5" y1="9.5" x2="13" y2="9.5" stroke-width={strokeWidth * 0.8} opacity="0.7"/>
		<line x1="5" y1="12.5" x2="10" y2="12.5" stroke-width={strokeWidth * 0.8} opacity="0.7"/>
	</svg>
{:else if name === 'tickets'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<path d="M3 9a2 2 0 0 0 0 4v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a2 2 0 0 0 0-4V8a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v1z" />
		<line x1="9" y1="6" x2="9" y2="18" stroke-dasharray="1.5 2" />
	</svg>
{:else if name === 'plugins'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<rect x="7" y="5" width="10" height="9" rx="2" />
		<line x1="9" y1="2" x2="9" y2="5" />
		<line x1="15" y1="2" x2="15" y2="5" />
		<line x1="12" y1="14" x2="12" y2="17" />
		<path d="M9 17 Q9 21 12 21 Q15 21 15 17" />
	</svg>
{:else if name === 'shells'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<rect x="5" y="7" width="16" height="13" rx="2" />
		<rect x="3" y="4" width="16" height="13" rx="2" />
		<line x1="3" y1="8" x2="19" y2="8" />
		<polyline points="6.5,11.5 8.5,13 6.5,14.5" />
	</svg>
{:else if name === 'memory'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<rect x="7" y="7" width="10" height="10" rx="1" />
		<line x1="10" y1="3" x2="10" y2="7" />
		<line x1="14" y1="3" x2="14" y2="7" />
		<line x1="10" y1="17" x2="10" y2="21" />
		<line x1="14" y1="17" x2="14" y2="21" />
		<line x1="3" y1="10" x2="7" y2="10" />
		<line x1="3" y1="14" x2="7" y2="14" />
		<line x1="17" y1="10" x2="21" y2="10" />
		<line x1="17" y1="14" x2="21" y2="14" />
	</svg>
{:else if name === 'settings'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<circle cx="12" cy="12" r="3" />
		<path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
	</svg>
{:else if name === 'archived'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<rect x="3" y="4" width="18" height="4" rx="1" />
		<rect x="3" y="8" width="18" height="12" rx="1" />
		<line x1="9" y1="14" x2="15" y2="14" />
	</svg>
{:else if name === 'about'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round">
		<circle cx="12" cy="4" r="1.5" />
		<line x1="9" y1="8" x2="15" y2="8" />
		<line x1="12" y1="8" x2="12" y2="20" />
		<line x1="8" y1="20" x2="16" y2="20" />
	</svg>
{/if}
