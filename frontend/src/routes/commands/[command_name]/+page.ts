import type { CommandDetailResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';
import { joinTitle } from '$lib/page-title';

export async function load({ params, fetch }) {
	const commandName = decodeURIComponent(params.command_name);

	const result = await safeFetch<CommandDetailResponse>(
		fetch,
		`${API_BASE}/commands/${encodeURIComponent(commandName)}/detail?per_page=100`
	);

	return {
		commandName,
		detail: result.ok ? result.data : null,
		title: joinTitle([`/${result.ok ? result.data.name : commandName}`, 'Commands'])
	};
}
