import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import type { HookScriptDetail } from '$lib/api-types';
import { createHighlighter } from 'shiki';

const LANGUAGE_MAP: Record<string, string> = {
	python: 'python',
	node: 'javascript',
	shell: 'bash',
	bash: 'bash'
};

let highlighterPromise: ReturnType<typeof createHighlighter> | null = null;

function getHighlighter() {
	if (!highlighterPromise) {
		highlighterPromise = createHighlighter({
			themes: ['github-dark'],
			langs: ['python', 'javascript', 'bash']
		});
	}
	return highlighterPromise;
}

export async function load({ params, fetch }) {
	const data = await fetchWithFallback<HookScriptDetail>(
		fetch,
		`${API_BASE}/hooks/scripts/${encodeURIComponent(params.filename)}`,
		{
			script: {
				filename: params.filename,
				language: 'unknown',
				source_name: '',
				event_types: [],
				registrations: 0,
				is_symlink: false
			},
			source_type: 'global',
			content: null,
			size_bytes: null,
			modified_at: null,
			line_count: null,
			error: 'file_not_found'
		}
	);

	let highlightedHtml: string | null = null;

	if (data.content) {
		try {
			const highlighter = await getHighlighter();
			const lang = LANGUAGE_MAP[data.script.language] || 'text';
			highlightedHtml = highlighter.codeToHtml(data.content, {
				lang,
				theme: 'github-dark'
			});
		} catch {
			// Fallback: no highlighting
			highlightedHtml = null;
		}
	}

	return {
		detail: data,
		highlightedHtml,
		filename: params.filename
	};
}
