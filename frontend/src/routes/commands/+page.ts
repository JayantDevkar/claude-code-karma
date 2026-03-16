import type { CommandUsage } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

interface CommandItem {
	name: string;
	path: string;
	type: 'file' | 'directory';
	size_bytes: number;
	modified_at: string;
}

export async function load({ fetch }) {
	const [usage, files] = await Promise.all([
		fetchWithFallback<CommandUsage[]>(fetch, `${API_BASE}/commands/usage`, []),
		fetchWithFallback<CommandItem[]>(fetch, `${API_BASE}/commands`, [])
	]);

	const usedNames = new Set(usage.map((c) => c.name));

	const fromFiles: CommandUsage[] = files
		.filter((item) => item.type === 'file' && item.name.endsWith('.md') && !usedNames.has(item.name.replace(/\.md$/, '')))
		.map((item) => ({
			name: item.name.replace(/\.md$/, ''),
			count: 0,
			is_plugin: false,
			plugin: null,
			last_used: null,
			session_count: 0,
			category: 'user_command' as const,
			description: null
		}));

	return {
		usage: [...usage, ...fromFiles]
	};
}
