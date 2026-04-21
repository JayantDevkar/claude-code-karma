import { Chart } from 'chart.js';

const MONO_STACK = "'Geist Mono', 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";
const SANS_STACK = "'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";

/**
 * Resolve theme colors from CSS custom properties. Chart.js cannot accept
 * raw `var(--x)` strings — it needs concrete color values at option time.
 * Read fresh on every config call so theme toggles pick up the new palette
 * when the consumer rebuilds the chart.
 */
export function getThemeColors() {
	if (typeof window === 'undefined') {
		return {
			primary: '#a87c1e',
			text: '#1b1712',
			textSecondary: '#47403a',
			textMuted: '#766d60',
			border: 'rgba(27,23,18,0.11)',
			bgBase: '#f3ede1',
			bgMuted: '#dfd4bd',
			bgSubtle: '#ebe3d2'
		};
	}
	const style = getComputedStyle(document.documentElement);
	const read = (name: string, fallback: string) =>
		style.getPropertyValue(name).trim() || fallback;
	return {
		primary: read('--accent', '#a87c1e'),
		text: read('--text-primary', '#1b1712'),
		textSecondary: read('--text-secondary', '#47403a'),
		textMuted: read('--text-muted', '#766d60'),
		border: read('--border', 'rgba(27,23,18,0.11)'),
		bgBase: read('--bg-base', '#f3ede1'),
		bgMuted: read('--bg-muted', '#dfd4bd'),
		bgSubtle: read('--bg-subtle', '#ebe3d2')
	};
}

/**
 * Register global Chart.js defaults. Call once on app init.
 */
export function registerChartDefaults() {
	const c = getThemeColors();
	Chart.defaults.font.family = MONO_STACK;
	Chart.defaults.color = c.textSecondary;
}

/**
 * Base chart config with tooltip + legend styling resolved to concrete
 * theme colors. Rebuild the chart to respond to a theme toggle.
 */
export function createResponsiveConfig(maintainAspectRatio = false) {
	const c = getThemeColors();
	return {
		responsive: true,
		maintainAspectRatio,
		plugins: {
			legend: {
				labels: {
					color: c.textSecondary,
					font: {
						family: MONO_STACK,
						size: 11
					}
				}
			},
			tooltip: {
				backgroundColor: c.bgBase,
				titleColor: c.text,
				bodyColor: c.textSecondary,
				borderColor: c.border,
				borderWidth: 1,
				padding: 10,
				cornerRadius: 6,
				displayColors: false,
				titleFont: {
					family: SANS_STACK,
					weight: 600
				},
				bodyFont: {
					family: MONO_STACK
				}
			}
		}
	};
}

/**
 * Common scale config for axis-style charts, with resolved colors.
 */
export function createCommonScaleConfig() {
	const c = getThemeColors();
	return {
		x: {
			grid: {
				color: 'rgba(128, 128, 128, 0.1)',
				drawOnChartArea: false
			},
			ticks: {
				color: c.textMuted,
				font: {
					family: MONO_STACK,
					size: 10
				},
				maxRotation: 0
			}
		},
		y: {
			beginAtZero: true,
			grace: '20%',
			grid: {
				color: 'rgba(128, 128, 128, 0.1)'
			},
			ticks: {
				color: c.textMuted,
				font: {
					family: MONO_STACK,
					size: 10
				},
				precision: 0
			}
		}
	};
}

/**
 * Data palette for series colors. Pulled from --data-* tokens when available.
 */
export function getChartColorPalette(): string[] {
	if (typeof window === 'undefined') {
		return ['#a87c1e', '#3a5578', '#5a7140', '#a06030', '#8a3a3a'];
	}
	const style = getComputedStyle(document.documentElement);
	const read = (name: string, fallback: string) =>
		style.getPropertyValue(name).trim() || fallback;
	return [
		read('--data-primary', '#a87c1e'),
		read('--data-secondary', '#3a5578'),
		read('--data-tertiary', '#5a7140'),
		read('--data-quaternary', '#a06030'),
		read('--data-quinary', '#8a3a3a')
	];
}

/**
 * Larger palette for charts needing many distinct colors.
 * Kept in sync with the editorial ink palette.
 */
export const chartColorPalette = [
	'#a87c1e', // accent amber
	'#3a5578', // ink blue
	'#5a7140', // moss
	'#a06030', // terracotta
	'#8a3a3a', // oxblood
	'#63557b', // iris
	'#3a6868', // verdigris
	'#7a4868', // aubergine
	'#475088', // woad
	'#8a7230', // ochre
	'#956a30', // burnt amber
	'#5a5750', // graphite
	'#d69260', // warm orange (dark-mode dual)
	'#b19ad1', // pale iris
	'#7ab5a8', // teal
	'#d1b76a' // saffron
];

export function getChartColor(index: number): string {
	return chartColorPalette[index % chartColorPalette.length];
}
