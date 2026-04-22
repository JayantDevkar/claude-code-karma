/**
 * Pure serialization utilities for analytics export.
 * All functions here are side-effect-free and testable without a browser.
 */

export interface AnalyticsExportData {
	total_sessions: number;
	total_tokens: number;
	total_input_tokens: number;
	total_output_tokens: number;
	total_duration_seconds: number;
	estimated_cost_usd: number;
	models_categorized: Record<string, number>;
	cache_hit_rate: number;
	tools_used: Record<string, number>;
	sessions_by_date: Record<string, number>;
	projects_active: number;
	peak_hours: number[];
	time_distribution: {
		morning_pct: number;
		afternoon_pct: number;
		evening_pct: number;
		night_pct: number;
		dominant_period: string;
	};
}

/** Derive a safe filename slug from a filter label + extension. */
export function getExportFilename(filterLabel: string, ext: string): string {
	const slug = filterLabel
		.toLowerCase()
		.replace(/[\s\u2013\u2014]+/g, '-') // spaces, en-dash, em-dash → hyphen
		.replace(/[^a-z0-9-]/g, ''); // strip remaining special chars
	return `analytics-${slug}.${ext}`;
}

/**
 * Build a multi-section CSV string from analytics data.
 *
 * Structure:
 *   SUMMARY           — key/value aggregate stats
 *   DAILY SESSIONS    — date → session count time series
 *   MODEL DISTRIBUTION — model → count + percentage
 *   TOOLS USED        — tool → count
 */
export function buildAnalyticsCSV(data: AnalyticsExportData, filterLabel: string): string {
	const lines: string[] = [];

	const row = (...cells: (string | number)[]) =>
		lines.push(
			cells
				.map((c) => {
					const s = String(c);
					return /[,"\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
				})
				.join(',')
		);
	const blank = () => lines.push('');
	const heading = (title: string) => lines.push(title);

	// ── Summary ──────────────────────────────────────────────────────────────
	heading('SUMMARY');
	row('metric', 'value');
	row('filter', filterLabel);
	row('generated_at', new Date().toISOString());
	row('total_sessions', data.total_sessions);
	row('total_tokens', data.total_tokens);
	row('total_input_tokens', data.total_input_tokens);
	row('total_output_tokens', data.total_output_tokens);
	row('estimated_cost_usd', data.estimated_cost_usd);
	row('cache_hit_rate_pct', (data.cache_hit_rate * 100).toFixed(2));
	row('total_duration_hours', (data.total_duration_seconds / 3600).toFixed(2));
	row('projects_active', data.projects_active);
	row('peak_hours', data.peak_hours.join(';'));
	row('dominant_time_period', data.time_distribution.dominant_period);
	blank();

	// ── Daily sessions ────────────────────────────────────────────────────────
	heading('DAILY SESSIONS');
	row('date', 'sessions');
	for (const date of Object.keys(data.sessions_by_date).sort()) {
		row(date, data.sessions_by_date[date]);
	}
	blank();

	// ── Model distribution ────────────────────────────────────────────────────
	heading('MODEL DISTRIBUTION');
	row('model', 'sessions', 'percentage');
	const totalModels = Object.values(data.models_categorized).reduce((s, v) => s + v, 0);
	for (const [model, count] of Object.entries(data.models_categorized).sort(
		(a, b) => b[1] - a[1]
	)) {
		const pct = totalModels > 0 ? ((count / totalModels) * 100).toFixed(1) : '0.0';
		row(model, count, pct);
	}
	blank();

	// ── Tools used ────────────────────────────────────────────────────────────
	heading('TOOLS USED');
	row('tool', 'count');
	for (const [tool, count] of Object.entries(data.tools_used).sort((a, b) => b[1] - a[1])) {
		row(tool, count);
	}

	return lines.join('\n');
}

/** Serialize analytics data to a pretty-printed JSON string. */
export function buildAnalyticsJSON(data: AnalyticsExportData, filterLabel: string): string {
	return JSON.stringify(
		{
			exported_at: new Date().toISOString(),
			filter: filterLabel,
			analytics: data
		},
		null,
		2
	);
}
