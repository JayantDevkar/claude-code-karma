import type { SkillUsage } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface SkillItem {
	name: string;
	path: string;
	type: 'file' | 'directory';
	size_bytes: number;
	modified_at: string;
}

export async function load({ fetch }) {
	const [usage, files, installedPluginSkills] = await Promise.all([
		fetchWithFallback<SkillUsage[]>(fetch, `${API_BASE}/skills/usage`, []),
		fetchWithFallback<SkillItem[]>(fetch, `${API_BASE}/skills`, []),
		fetchWithFallback<Array<{ name: string; plugin: string; category: string }>>(
			fetch,
			`${API_BASE}/plugins/installed-skills`,
			[]
		)
	]);

	const usedNames = new Set(usage.map((s) => s.name));

	const fromFiles: SkillUsage[] = files
		.filter((item) => item.type === 'directory' && !usedNames.has(item.name))
		.map((item) => ({
			name: item.name,
			count: 0,
			is_plugin: false,
			plugin: null,
			last_used: null,
			session_count: 0,
			category: 'custom_skill' as const,
			description: null
		}));

	const fromPlugins: SkillUsage[] = installedPluginSkills
		.filter((item) => !usedNames.has(item.name))
		.map((item) => ({
			name: item.name,
			count: 0,
			is_plugin: true,
			plugin: item.plugin.split('@')[0],
			last_used: null,
			session_count: 0,
			category: 'plugin_skill' as const,
			description: null
		}));

	return {
		usage: [...usage, ...fromFiles, ...fromPlugins]
	};
}
