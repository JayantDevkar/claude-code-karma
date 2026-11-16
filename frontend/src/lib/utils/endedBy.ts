import { formatDate } from '$lib/utils';

import type { EndedBy } from '$lib/api-types';

export type { EndedBy };
export type EndedByTone = 'warning' | 'error' | 'muted';

export interface EndedByInfo {
	label: string;
	tone: EndedByTone;
	tooltip: string;
}

// Label, tone and tooltip for how a session or subagent ended; null when nothing notable.
export function endedByLabel(
	endedBy: EndedBy | null | undefined,
	resetsAt: string | null | undefined,
	now: Date
): EndedByInfo | null {
	switch (endedBy) {
		case 'limit': {
			const reset = resetsAt ? new Date(resetsAt) : null;
			const future = reset !== null && !isNaN(reset.getTime()) && reset.getTime() > now.getTime();
			const label = future ? `Stopped by limit · resets ${formatDate(resetsAt as string)}` : 'Stopped by limit';
			return {
				label,
				tone: 'warning',
				tooltip: 'The last turn was cut off by a usage limit.'
			};
		}
		case 'refusal':
			return {
				label: 'Refused',
				tone: 'error',
				tooltip: 'The last turn ended with a refusal from the model.'
			};
		case 'api_error':
			return {
				label: 'Ended on API error',
				tone: 'muted',
				tooltip: 'The last turn ended with an API error.'
			};
		default:
			return null;
	}
}
