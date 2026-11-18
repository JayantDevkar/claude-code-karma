import DOMPurify from 'isomorphic-dompurify';

// Tags that style the page, fetch a remote resource as soon as they render, or collect input.
const FORBIDDEN_TAGS = [
	'style',
	'video',
	'audio',
	'source',
	'track',
	'picture',
	'form',
	'button',
	'select',
	'textarea',
	'dialog'
];

// Attributes a body could use to style itself, take focus, collide with page ids or post data.
const FORBIDDEN_ATTRS = [
	'style',
	'srcset',
	'background',
	'id',
	'tabindex',
	'autofocus',
	'accesskey',
	'contenteditable',
	'popover',
	'popovertarget',
	'popovertargetaction',
	'action',
	'formaction'
];

// The one class the markdown renderer itself writes: the language of a fenced code block.
const CODE_LANGUAGE_CLASS = /^language-[\w+#.-]+$/;

function isInlineImage(src: string | null): boolean {
	return !!src && /^data:image\//i.test(src.trim());
}

// Keep `language-*` on code blocks; any other class would let a body use the app's own utility classes.
function stripClasses(root: DocumentFragment): void {
	for (const el of Array.from(root.querySelectorAll('[class]'))) {
		const isCode = el.tagName === 'CODE' || el.tagName === 'PRE';
		const kept = isCode
			? Array.from(el.classList).filter((name) => CODE_LANGUAGE_CLASS.test(name))
			: [];
		if (kept.length > 0) el.setAttribute('class', kept.join(' '));
		else el.removeAttribute('class');
	}
}

// A task-list checkbox becomes a plain mark; every other input is removed.
function replaceInputs(root: DocumentFragment): void {
	for (const input of Array.from(root.querySelectorAll('input'))) {
		if (input.getAttribute('type') === 'checkbox') {
			input.replaceWith(document.createTextNode(input.hasAttribute('checked') ? '☑ ' : '☐ '));
		} else {
			input.remove();
		}
	}
}

// A remote image becomes a plain link, so nothing is fetched just by rendering the body.
function replaceRemoteImages(root: DocumentFragment): void {
	for (const img of Array.from(root.querySelectorAll('img'))) {
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
}

/** Sanitize an event body written by another party: it cannot style itself, load media or show forms. */
export function sanitizeEventHtml(html: string): string {
	const canRewrite = typeof document !== 'undefined';
	const clean = DOMPurify.sanitize(html, {
		USE_PROFILES: { html: true },
		// Without a DOM for the second pass, drop what that pass would have rewritten.
		FORBID_ATTR: canRewrite ? FORBIDDEN_ATTRS : [...FORBIDDEN_ATTRS, 'class'],
		FORBID_TAGS: canRewrite ? FORBIDDEN_TAGS : [...FORBIDDEN_TAGS, 'img', 'input']
	});
	if (!canRewrite) return clean;

	// A template's content is inert, so nothing loads or runs while it is rewritten.
	const template = document.createElement('template');
	template.innerHTML = clean;
	stripClasses(template.content);
	replaceInputs(template.content);
	replaceRemoteImages(template.content);
	return template.innerHTML;
}
