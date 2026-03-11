import { Chart } from 'chart.js';

/**
 * Get theme colors from CSS custom properties.
 * Chart.js renders on <canvas> via the Canvas 2D API, which does NOT support
 * CSS variable strings. Always resolve variables to actual color values before
 * passing them to Chart.js.
 * @returns Object containing commonly used theme colors as resolved hex/rgb values
 */
export function getThemeColors() {
	const style = getComputedStyle(document.documentElement);
	return {
		primary: style.getPropertyValue('--accent').trim(),
		text: style.getPropertyValue('--text-primary').trim(),
		textSecondary: style.getPropertyValue('--text-secondary').trim(),
		textMuted: style.getPropertyValue('--text-muted').trim(),
		textFaint: style.getPropertyValue('--text-faint').trim(),
		border: style.getPropertyValue('--border').trim(),
		bgBase: style.getPropertyValue('--bg-base').trim(),
		bgMuted: style.getPropertyValue('--bg-muted').trim(),
		bgSubtle: style.getPropertyValue('--bg-subtle').trim()
	};
}

/**
 * Register global Chart.js defaults for consistent styling across all charts.
 * Must be called from onMount (needs DOM access to resolve CSS variables).
 */
export function registerChartDefaults() {
	const colors = getThemeColors();
	Chart.defaults.font.family = 'JetBrains Mono, monospace';
	Chart.defaults.color = colors.textSecondary;
}

/**
 * Create a responsive chart configuration with common options.
 * All colors are resolved from CSS custom properties at call time.
 * @param maintainAspectRatio - Whether to maintain aspect ratio (default: false for better container fitting)
 * @returns Base configuration object that can be spread into chart options
 */
export function createResponsiveConfig(maintainAspectRatio = false) {
	const colors = getThemeColors();
	return {
		responsive: true,
		maintainAspectRatio,
		plugins: {
			legend: {
				labels: {
					color: colors.textSecondary,
					font: {
						family: 'JetBrains Mono, monospace',
						size: 11
					}
				}
			},
			tooltip: {
				backgroundColor: colors.bgBase,
				titleColor: colors.text,
				bodyColor: colors.textSecondary,
				borderColor: colors.border,
				borderWidth: 1,
				padding: 10,
				cornerRadius: 8,
				displayColors: false, // Cleaner look without color box
				titleFont: {
					family: 'Inter, sans-serif',
					weight: 600
				},
				bodyFont: {
					family: 'JetBrains Mono, monospace'
				}
			}
		}
	};
}

/**
 * Create common scale configuration for line charts.
 * All colors are resolved from CSS custom properties at call time.
 * @returns Scale configuration object for x and y axes
 */
export function createCommonScaleConfig() {
	const colors = getThemeColors();
	return {
		x: {
			grid: {
				color: 'rgba(128, 128, 128, 0.1)', // Neutral gray works in both themes
				drawOnChartArea: false
			},
			ticks: {
				color: colors.textMuted,
				font: {
					family: 'JetBrains Mono, monospace',
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
				color: colors.textMuted,
				font: {
					family: 'JetBrains Mono, monospace',
					size: 10
				},
				precision: 0
			}
		}
	};
}

/**
 * Watch for theme changes (data-theme attribute on <html>) and invoke callback.
 * Returns a cleanup function to disconnect the observer.
 * Use in onMount/onDestroy to recreate charts with updated colors.
 */
export function onThemeChange(callback: () => void): () => void {
	const observer = new MutationObserver((mutations) => {
		for (const mutation of mutations) {
			if (mutation.type === 'attributes' && mutation.attributeName === 'data-theme') {
				callback();
			}
		}
	});
	observer.observe(document.documentElement, {
		attributes: true,
		attributeFilter: ['data-theme']
	});
	return () => observer.disconnect();
}

/**
 * Get chart colors from CSS variables (for dynamic theme support)
 * Call this in onMount or use getComputedStyle for live values
 */
export function getChartColorPalette(): string[] {
	if (typeof window === 'undefined') {
		// SSR fallback
		return ['#7c3aed', '#3b82f6', '#10b981', '#f59e0b', '#ef4444'];
	}

	const style = getComputedStyle(document.documentElement);
	return [
		style.getPropertyValue('--data-primary').trim() || '#7c3aed',
		style.getPropertyValue('--data-secondary').trim() || '#3b82f6',
		style.getPropertyValue('--data-tertiary').trim() || '#10b981',
		style.getPropertyValue('--data-quaternary').trim() || '#f59e0b',
		style.getPropertyValue('--data-quinary').trim() || '#ef4444'
	];
}

/**
 * Color palette for charts (legacy export for backwards compatibility)
 * Note: These CSS variables may not work directly with Chart.js
 * Use getChartColorPalette() in onMount for computed values
 */
export const chartColorPalette = [
	'#7c3aed', // accent (purple)
	'#3b82f6', // blue
	'#10b981', // green
	'#f59e0b', // amber
	'#ef4444', // red
	'#ec4899', // pink
	'#8b5cf6', // violet
	'#06b6d4', // cyan
	'#84cc16', // lime
	'#f97316', // orange
	'#6366f1', // indigo
	'#14b8a6', // teal
	'#a855f7', // purple
	'#eab308', // yellow
	'#0ea5e9', // sky
	'#d946ef' // fuchsia
];

/**
 * Get a color from the palette, cycling if index exceeds palette length
 */
export function getChartColor(index: number): string {
	return chartColorPalette[index % chartColorPalette.length];
}
