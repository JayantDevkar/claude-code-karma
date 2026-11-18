import DOMPurify from 'isomorphic-dompurify';

// Tags that style the page or fetch a remote resource as soon as they render.
const FORBIDDEN_TAGS = ['style', 'video', 'audio', 'source', 'track', 'picture'];

function isInlineImage(src: string | null): boolean {
	return !!src && /^data:image\//i.test(src.trim());
}

/** Sanitize an event body written by another party: no inline styles, no remote media. */
export function sanitizeEventHtml(html: string): string {
	const canRewrite = typeof document !== 'undefined';
	const clean = DOMPurify.sanitize(html, {
		USE_PROFILES: { html: true },
		FORBID_ATTR: ['style', 'srcset', 'background'],
		// Without a DOM to rewrite images in, drop them outright.
		FORBID_TAGS: canRewrite ? FORBIDDEN_TAGS : [...FORBIDDEN_TAGS, 'img']
	});
	if (!canRewrite || !/<img/i.test(clean)) return clean;

	// A template's content is inert, so nothing loads while images are swapped out.
	const template = document.createElement('template');
	template.innerHTML = clean;
	for (const img of Array.from(template.content.querySelectorAll('img'))) {
		const src = img.getAttribute('src');
		if (isInlineImage(src)) continue;
		const label = img.getAttribute('alt') || src || 'image';
		if (src && /^https?:\/\//i.test(src)) {
			const link = document.createElement('a');
			link.setAttribute('href', src);
			link.setAttribute('target', '_blank');
			link.setAttribute('rel', 'noopener noreferrer nofollow');
			link.textContent = `Image: ${label}`;
			img.replaceWith(link);
		} else {
			img.replaceWith(document.createTextNode(`Image: ${label}`));
		}
	}
	return template.innerHTML;
}
