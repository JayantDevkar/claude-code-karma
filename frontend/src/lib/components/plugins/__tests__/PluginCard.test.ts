import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import PluginCard from '../PluginCard.svelte';
import type { PluginSummary } from '$lib/api-types';

const base: PluginSummary = {
	name: 'superpowers',
	installation_count: 1,
	scopes: ['user'],
	latest_version: '1.2.3',
	latest_update: null,
	agent_count: 1,
	skill_count: 2,
	command_count: 3,
	total_runs: 0,
	estimated_cost_usd: 0,
	days_since_update: 4,
	description: null,
	is_official: false
};

function costText(plugin: PluginSummary, usage: 'ready' | 'missing' = 'ready') {
	const { container } = render(PluginCard, { props: { plugin, usage } });
	return container.textContent ?? '';
}

describe('PluginCard cost', () => {
	afterEach(() => cleanup());

	it('shows a known zero as $0.00, not the "--" placeholder', () => {
		const text = costText(base);
		expect(text).toContain('$0.00');
		expect(text).not.toContain('--');
	});

	it('formats a positive cost', () => {
		expect(costText({ ...base, estimated_cost_usd: 1.5 })).toContain('$1.50');
	});

	it('shows — when the usage fetch failed', () => {
		const text = costText(base, 'missing');
		expect(text).toContain('—');
		expect(text).not.toContain('$0.00');
	});

	it('renders the plugin name as an h2 under the page h1', () => {
		const { getByRole } = render(PluginCard, { props: { plugin: base } });
		expect(getByRole('heading', { level: 2, name: 'superpowers' })).toBeTruthy();
	});
});
