import { describe, it, expect } from 'vitest';
import {
	buildAnalyticsCSV,
	buildAnalyticsJSON,
	getExportFilename,
	type AnalyticsExportData
} from '$lib/utils/analytics-export';

// ─────────────────────────────────────────────────────────────────────────────
// Shared fixture
// ─────────────────────────────────────────────────────────────────────────────

const baseAnalytics: AnalyticsExportData = {
	total_sessions: 42,
	total_tokens: 500000,
	total_input_tokens: 300000,
	total_output_tokens: 200000,
	total_duration_seconds: 7200,
	estimated_cost_usd: 1.5,
	cache_hit_rate: 0.85,
	projects_active: 3,
	peak_hours: [9, 10, 11],
	models_categorized: { Sonnet: 30, Haiku: 12 },
	tools_used: { Read: 100, Write: 50, Bash: 25 },
	sessions_by_date: {
		'2024-01-03': 5,
		'2024-01-01': 10,
		'2024-01-02': 7
	},
	time_distribution: {
		morning_pct: 40,
		afternoon_pct: 35,
		evening_pct: 20,
		night_pct: 5,
		dominant_period: 'Morning'
	}
};

const emptyAnalytics: AnalyticsExportData = {
	total_sessions: 0,
	total_tokens: 0,
	total_input_tokens: 0,
	total_output_tokens: 0,
	total_duration_seconds: 0,
	estimated_cost_usd: 0,
	cache_hit_rate: 0,
	projects_active: 0,
	peak_hours: [],
	models_categorized: {},
	tools_used: {},
	sessions_by_date: {},
	time_distribution: {
		morning_pct: 0,
		afternoon_pct: 0,
		evening_pct: 0,
		night_pct: 0,
		dominant_period: 'Unknown'
	}
};

// ─────────────────────────────────────────────────────────────────────────────
// getExportFilename
// ─────────────────────────────────────────────────────────────────────────────

describe('getExportFilename', () => {
	it('lowercases and hyphenates the filter label', () => {
		expect(getExportFilename('Last 30 Days', 'csv')).toBe('analytics-last-30-days.csv');
	});

	it('appends the given extension', () => {
		expect(getExportFilename('All Time', 'json')).toBe('analytics-all-time.json');
	});

	it('strips special characters from the label', () => {
		expect(getExportFilename('This Week (Mon–Sun)', 'png')).toBe(
			'analytics-this-week-mon-sun.png'
		);
	});

	it('handles a single-word label', () => {
		expect(getExportFilename('Today', 'csv')).toBe('analytics-today.csv');
	});

	it('collapses multiple spaces into a single hyphen each', () => {
		expect(getExportFilename('last  30  days', 'csv')).toBe('analytics-last-30-days.csv');
	});
});

// ─────────────────────────────────────────────────────────────────────────────
// buildAnalyticsCSV
// ─────────────────────────────────────────────────────────────────────────────

describe('buildAnalyticsCSV', () => {
	it('contains the SUMMARY section heading', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('SUMMARY');
	});

	it('includes all summary metrics', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('total_sessions,42');
		expect(csv).toContain('total_tokens,500000');
		expect(csv).toContain('total_input_tokens,300000');
		expect(csv).toContain('total_output_tokens,200000');
		expect(csv).toContain('estimated_cost_usd,1.5');
		expect(csv).toContain('projects_active,3');
	});

	it('formats cache_hit_rate as a percentage with 2 decimal places', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('cache_hit_rate_pct,85.00');
	});

	it('formats total_duration_hours to 2 decimal places', () => {
		// 7200 seconds = 2.00 hours
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('total_duration_hours,2.00');
	});

	it('includes the filter label in the summary', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'Last 7 Days');
		expect(csv).toContain('filter,Last 7 Days');
	});

	it('includes peak_hours semicolon-joined', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('peak_hours,9;10;11');
	});

	it('outputs daily sessions sorted by date ascending', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		const dateSection = csv.split('DAILY SESSIONS')[1].split('MODEL DISTRIBUTION')[0];
		const rows = dateSection
			.trim()
			.split('\n')
			.filter((r) => r.startsWith('2024'));
		expect(rows[0]).toContain('2024-01-01');
		expect(rows[1]).toContain('2024-01-02');
		expect(rows[2]).toContain('2024-01-03');
	});

	it('outputs correct session counts per date', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('2024-01-01,10');
		expect(csv).toContain('2024-01-02,7');
		expect(csv).toContain('2024-01-03,5');
	});

	it('contains the DAILY SESSIONS section heading', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('DAILY SESSIONS');
	});

	it('contains the MODEL DISTRIBUTION section heading', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('MODEL DISTRIBUTION');
	});

	it('calculates model percentages correctly', () => {
		// Sonnet: 30, Haiku: 12, total: 42 → Sonnet: 71.4%, Haiku: 28.6%
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('Sonnet,30,71.4');
		expect(csv).toContain('Haiku,12,28.6');
	});

	it('sorts models by count descending', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		const modelSection = csv.split('MODEL DISTRIBUTION')[1].split('TOOLS USED')[0];
		const rows = modelSection
			.trim()
			.split('\n')
			.filter((r) => !r.startsWith('model') && r.trim());
		// Sonnet (30) should come before Haiku (12)
		expect(rows[0]).toContain('Sonnet');
		expect(rows[1]).toContain('Haiku');
	});

	it('contains the TOOLS USED section heading', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		expect(csv).toContain('TOOLS USED');
	});

	it('outputs tools sorted by count descending', () => {
		const csv = buildAnalyticsCSV(baseAnalytics, 'All Time');
		const toolSection = csv.split('TOOLS USED')[1];
		const rows = toolSection
			.trim()
			.split('\n')
			.filter((r) => !r.startsWith('tool') && r.trim());
		expect(rows[0]).toContain('Read,100');
		expect(rows[1]).toContain('Write,50');
		expect(rows[2]).toContain('Bash,25');
	});

	it('handles zero cache_hit_rate without NaN', () => {
		const csv = buildAnalyticsCSV(emptyAnalytics, 'All Time');
		expect(csv).toContain('cache_hit_rate_pct,0.00');
		expect(csv).not.toContain('NaN');
	});

	it('handles empty sessions_by_date', () => {
		const csv = buildAnalyticsCSV(emptyAnalytics, 'All Time');
		expect(csv).toContain('DAILY SESSIONS');
		// Should not crash; header row should still be present
		expect(csv).toContain('date,sessions');
	});

	it('handles empty models_categorized with 0.0 percentage', () => {
		const csv = buildAnalyticsCSV(emptyAnalytics, 'All Time');
		expect(csv).toContain('MODEL DISTRIBUTION');
		// No model rows should appear — just the header
		const modelSection = csv.split('MODEL DISTRIBUTION')[1].split('TOOLS USED')[0];
		const rows = modelSection
			.trim()
			.split('\n')
			.filter((r) => r.trim() && !r.startsWith('model'));
		expect(rows.length).toBe(0);
	});

	it('handles empty tools_used', () => {
		const csv = buildAnalyticsCSV(emptyAnalytics, 'All Time');
		const toolSection = csv.split('TOOLS USED')[1];
		const rows = toolSection
			.trim()
			.split('\n')
			.filter((r) => r.trim() && !r.startsWith('tool'));
		expect(rows.length).toBe(0);
	});

	it('handles empty peak_hours', () => {
		const csv = buildAnalyticsCSV(emptyAnalytics, 'All Time');
		expect(csv).toContain('peak_hours,');
		expect(csv).not.toContain('NaN');
	});
});

// ─────────────────────────────────────────────────────────────────────────────
// buildAnalyticsJSON
// ─────────────────────────────────────────────────────────────────────────────

describe('buildAnalyticsJSON', () => {
	it('produces valid JSON', () => {
		const json = buildAnalyticsJSON(baseAnalytics, 'All Time');
		expect(() => JSON.parse(json)).not.toThrow();
	});

	it('includes the exported_at key', () => {
		const parsed = JSON.parse(buildAnalyticsJSON(baseAnalytics, 'All Time'));
		expect(parsed).toHaveProperty('exported_at');
	});

	it('exported_at is a valid ISO string', () => {
		const parsed = JSON.parse(buildAnalyticsJSON(baseAnalytics, 'All Time'));
		expect(() => new Date(parsed.exported_at)).not.toThrow();
		expect(new Date(parsed.exported_at).toISOString()).toBe(parsed.exported_at);
	});

	it('includes the filter label', () => {
		const parsed = JSON.parse(buildAnalyticsJSON(baseAnalytics, 'Last 30 Days'));
		expect(parsed.filter).toBe('Last 30 Days');
	});

	it('includes the analytics object', () => {
		const parsed = JSON.parse(buildAnalyticsJSON(baseAnalytics, 'All Time'));
		expect(parsed).toHaveProperty('analytics');
		expect(parsed.analytics.total_sessions).toBe(42);
	});

	it('preserves all analytics fields', () => {
		const parsed = JSON.parse(buildAnalyticsJSON(baseAnalytics, 'All Time'));
		const a = parsed.analytics;
		expect(a.total_tokens).toBe(500000);
		expect(a.estimated_cost_usd).toBe(1.5);
		expect(a.cache_hit_rate).toBe(0.85);
		expect(a.models_categorized).toEqual({ Sonnet: 30, Haiku: 12 });
		expect(a.sessions_by_date).toEqual(baseAnalytics.sessions_by_date);
	});

	it('is pretty-printed (contains newlines)', () => {
		const json = buildAnalyticsJSON(baseAnalytics, 'All Time');
		expect(json).toContain('\n');
	});

	it('handles empty analytics without throwing', () => {
		expect(() => buildAnalyticsJSON(emptyAnalytics, 'All Time')).not.toThrow();
	});
});
