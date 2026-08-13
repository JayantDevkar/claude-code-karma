/**
 * Search-match highlighting utilities, shared between the collapsed timeline
 * card (plain text) and the expanded/modal views (rendered markdown HTML).
 */

import DOMPurify from 'isomorphic-dompurify';

function escapeHtml(text: string): string {
	return text
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

function escapeRegExp(text: string): string {
	return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Highlight matches of `query` in plain (unescaped) text, returning HTML
 * safe for `{@html}`. Only safe for text that has NOT already been rendered
 * to HTML.
 *
 * Matching happens against the RAW text, then each segment is escaped on
 * the way out — matching against already-escaped text would let a query
 * like "lt" match inside an entity the escaping itself produced (turning
 * "a < b" into visible "a &lt; b"), and would make a query containing
 * `< > & "` unmatchable even though the raw text contains it literally.
 */
export function highlightPlainText(text: string, query: string): string {
	const trimmedQuery = query.trim();
	if (!trimmedQuery || !text) return escapeHtml(text);

	const regex = new RegExp(`(${escapeRegExp(trimmedQuery)})`, 'gi');
	let result = '';
	let lastIndex = 0;
	let match: RegExpExecArray | null;
	while ((match = regex.exec(text))) {
		result += escapeHtml(text.slice(lastIndex, match.index));
		result += `<mark class="search-highlight">${escapeHtml(match[0])}</mark>`;
		lastIndex = match.index + match[0].length;
	}
	result += escapeHtml(text.slice(lastIndex));
	return result;
}

/**
 * Highlight matches of `query` inside already-rendered (sanitized) HTML.
 * Walks text nodes only, so it can't corrupt tags/attributes or double-escape
 * content — safe to run on markdown output from `marked` + DOMPurify.
 */
export function highlightHtmlContent(html: string, query: string): string {
	const trimmedQuery = query.trim();
	if (!trimmedQuery || !html || typeof document === 'undefined') return html;

	const regex = new RegExp(`(${escapeRegExp(trimmedQuery)})`, 'gi');
	const container = document.createElement('div');
	container.innerHTML = html;

	const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
	const textNodes: Text[] = [];
	let node: Node | null;
	while ((node = walker.nextNode())) {
		textNodes.push(node as Text);
	}

	for (const textNode of textNodes) {
		const value = textNode.nodeValue ?? '';
		regex.lastIndex = 0;
		if (!regex.test(value)) continue;
		regex.lastIndex = 0;

		const fragment = document.createDocumentFragment();
		let lastIndex = 0;
		let match: RegExpExecArray | null;
		while ((match = regex.exec(value))) {
			if (match.index > lastIndex) {
				fragment.appendChild(document.createTextNode(value.slice(lastIndex, match.index)));
			}
			const mark = document.createElement('mark');
			mark.className = 'search-highlight';
			mark.textContent = match[0];
			fragment.appendChild(mark);
			lastIndex = match.index + match[0].length;
		}
		if (lastIndex < value.length) {
			fragment.appendChild(document.createTextNode(value.slice(lastIndex)));
		}
		textNode.parentNode?.replaceChild(fragment, textNode);
	}

	// Belt-and-suspenders: content is already safe (built via createElement/
	// textContent above), but this feeds {@html} so re-sanitize anyway.
	return DOMPurify.sanitize(container.innerHTML);
}
