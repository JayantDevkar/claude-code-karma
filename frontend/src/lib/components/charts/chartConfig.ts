import { Chart, type ChartConfiguration } from 'chart.js';

/**
 * Register global Chart.js defaults for consistent styling across all charts
 * Should be called once during app initialization or in each chart component's onMount
 */
export function registerChartDefaults() {
	Chart.defaults.font.family = 'JetBrains Mono, monospace';
	Chart.defaults.color = 'var(--text-secondary)';
}

/**
 * Create a responsive chart configuration with common options
 * @param maintainAspectRatio - Whether to maintain aspect ratio (default: false for better container fitting)
 * @returns Base configuration object that can be spread into chart options
 */
export function createResponsiveConfig(maintainAspectRatio = false) {
	return {
		responsive: true,
		maintainAspectRatio,
		plugins: {
			legend: {
				labels: {
					color: 'var(--text-secondary)',
					font: {
						family: 'JetBrains Mono, monospace',
						size: 11
					}
				}
			},
			tooltip: {
				backgroundColor: 'var(--bg-base)', // High contrast background
				titleColor: 'var(--text-primary)',
				bodyColor: 'var(--text-secondary)',
				borderColor: 'var(--border)',
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
 * Get theme colors from CSS custom properties
 * Useful for dynamic color assignment based on current theme
 * @returns Object containing commonly used theme colors
 */
export function getThemeColors() {
	const style = getComputedStyle(document.documentElement);
	return {
		primary: style.getPropertyValue('--accent').trim(),
		text: style.getPropertyValue('--text-primary').trim(),
		textSecondary: style.getPropertyValue('--text-secondary').trim(),
		textMuted: style.getPropertyValue('--text-muted').trim(),
		border: style.getPropertyValue('--border').trim(),
		bgBase: style.getPropertyValue('--bg-base').trim(),
		bgMuted: style.getPropertyValue('--bg-muted').trim(),
		bgSubtle: style.getPropertyValue('--bg-subtle').trim()
	};
}

/**
 * Create common scale configuration for line charts
 * @returns Scale configuration object for x and y axes
 */
export function createCommonScaleConfig() {
	return {
		x: {
			grid: {
				color: 'rgba(128, 128, 128, 0.1)', // Subtle grid lines works in light and dark
				drawOnChartArea: false
			},
			ticks: {
				color: 'var(--text-muted)',
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
				color: 'rgba(128, 128, 128, 0.1)' // Subtle grid lines
			},
			ticks: {
				color: 'var(--text-muted)',
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
