import type { SkillDetailResponse } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

export async function load({ params, fetch }) {
	const skillName = decodeURIComponent(params.skill_name);

	const result = await safeFetch<SkillDetailResponse>(
		fetch,
		`${API_BASE}/skills/${encodeURIComponent(skillName)}/detail?per_page=100`
	);

	return {
		skillName,
		detail: result.ok ? result.data : null
	};
}
