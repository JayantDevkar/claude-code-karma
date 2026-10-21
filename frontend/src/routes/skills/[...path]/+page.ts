import { joinTitle } from '$lib/page-title';

export function load({ params }) {
	return { title: joinTitle([params.path.split('/').pop() || 'Skill', 'Skills']) };
}
