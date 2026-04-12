/**
 * Svelte action that injects per-section and per-code-block copy buttons
 * into a `.markdown-preview` container after `{@html}` has populated the DOM.
 *
 * Uses a MutationObserver to detect when {@html} changes the DOM — more
 * reliable than queueMicrotask because it fires AFTER the DOM mutation,
 * regardless of Svelte's internal flush ordering.
 *
 * Section detection covers two patterns Claude actually uses:
 *   1. Proper markdown headings — <h2> and <h3>
 *   2. Bold-only paragraphs — <p><strong>Title</strong></p> preceded by <hr>
 *      (Claude's **Title** + --- style)
 *
 * Buttons are only injected when a section's content meets MIN_SECTION_CHARS.
 * This is heading-level agnostic: a meaty h3 gets a button, a one-liner h2
 * does not. Code block copy buttons are always injected regardless of length.
 *
 * h2 sections include all h3 content beneath them in their character count,
 * so a document with one h2 title + several h3 steps will correctly show
 * a button on the h2 (whole plan) AND on each substantive h3 step.
 */

/** Minimum plain-text characters a section must contain to earn a copy button. */
const MIN_SECTION_CHARS = 150;

const COPY_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`;
const CHECK_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeCopyButton(extraClass: string, label: string): HTMLButtonElement {
	const btn = document.createElement('button');
	btn.className = `md-copy-btn ${extraClass}`;
	btn.setAttribute('aria-label', label);
	// No title attribute — aria-label handles accessibility and avoids the
	// native browser tooltip (which has an OS-imposed delay and can't be styled).
	btn.innerHTML = COPY_ICON;
	btn.type = 'button';
	return btn;
}

function flashCopied(btn: HTMLButtonElement): ReturnType<typeof setTimeout> {
	btn.innerHTML = CHECK_ICON;
	btn.classList.add('md-copy-btn--copied');
	return setTimeout(() => {
		btn.innerHTML = COPY_ICON;
		btn.classList.remove('md-copy-btn--copied');
	}, 2000);
}

/**
 * Returns true if the element is a paragraph whose only non-whitespace child
 * is a single <strong> — Claude's **bold heading** pattern.
 */
function isBoldHeading(el: Element): boolean {
	if (el.tagName !== 'P') return false;
	const meaningful = Array.from(el.childNodes).filter(
		(n) => !(n.nodeType === Node.TEXT_NODE && n.textContent?.trim() === '')
	);
	return (
		meaningful.length === 1 &&
		meaningful[0].nodeType === Node.ELEMENT_NODE &&
		(meaningful[0] as Element).tagName === 'STRONG'
	);
}

/**
 * What heading level stops the current section?
 *
 * h2 section  → stops at next h2, HR, or top-level bold paragraph
 * h3 section  → stops at next h2, h3, HR, or top-level bold paragraph
 * bold-para   → stops at next HR, h2, or top-level bold paragraph
 */
function isSectionBoundary(el: Element, startTag: string): boolean {
	const tag = el.tagName;
	if (tag === 'HR' || tag === 'H2') return true;
	if (startTag === 'H3' && tag === 'H3') return true;
	// A bold paragraph that directly follows an HR is a top-level section title
	if (isBoldHeading(el)) {
		const prev = el.previousElementSibling;
		if (prev === null || prev.tagName === 'HR') return true;
	}
	return false;
}

/**
 * Collect all plain text from `startEl` through siblings until the next
 * section boundary. Returns { text, charCount }.
 *
 * The heading/title text itself is included so copy output is self-contained.
 * charCount measures only the *prose* body content (siblings after the heading,
 * excluding <pre> code blocks) so that a heading whose body is entirely code
 * blocks — which already have their own copy buttons — doesn't pass the
 * threshold. The full text for copying still includes code block content.
 */
function collectSection(startEl: Element): { text: string; charCount: number } {
	const startTag = startEl.tagName; // H2, H3, or P
	const titleText = (startEl.textContent ?? '').trim();

	const bodyParts: string[] = [];
	let proseCharCount = 0;
	let sibling = startEl.nextElementSibling;

	while (sibling) {
		if (isSectionBoundary(sibling, startTag)) break;
		const t = (sibling.textContent ?? '').trim();
		if (t) {
			bodyParts.push(t);
			// Only count prose chars towards threshold — exclude <pre> blocks
			// since those already have their own copy buttons
			if (sibling.tagName !== 'PRE') {
				proseCharCount += t.length;
			}
		}
		sibling = sibling.nextElementSibling;
	}

	const text = [titleText, ...bodyParts].filter(Boolean).join('\n\n');
	return { text, charCount: proseCharCount };
}

// ─── Action ──────────────────────────────────────────────────────────────────

export function markdownCopyButtons(node: HTMLElement, _content?: string) {
	let setupPending = false;

	function attachButton(
		anchorEl: HTMLElement,
		extraClass: string,
		label: string,
		getText: () => string
	) {
		const btn = makeCopyButton(extraClass, label);
		let timer: ReturnType<typeof setTimeout>;

		const onClick = (e: Event) => {
			e.stopPropagation();
			navigator.clipboard.writeText(getText()).then(() => {
				clearTimeout(timer);
				timer = flashCopied(btn);
			});
		};

		btn.addEventListener('click', onClick);
		anchorEl.appendChild(btn);
	}

	function setup() {
		// Remove any previously injected buttons
		node.querySelectorAll('.md-copy-btn').forEach((el) => el.remove());

		// ── Code blocks — always injected, no length gate ────────────────────
		// Code is the most-copied thing; length is irrelevant.
		node.querySelectorAll<HTMLPreElement>('pre').forEach((pre) => {
			attachButton(pre, 'md-copy-btn--code', 'Copy code', () => {
				const code = pre.querySelector('code');
				return (code ?? pre).textContent ?? '';
			});
		});

		// ── Headings (h1, h2, h3) ────────────────────────────────────────────
		//
		// h1 and h2 ALWAYS get a button (top-level sections — matches the
		// "every H1 and H2 gets a copy option" promise in the PR description).
		// h3 is gated by MIN_SECTION_CHARS so trivial subheadings don't clutter
		// the UI.
		//
		// h2 sections walk past h3 boundaries in collectSection(), so the h2
		// button copies the entire h2 subtree including its h3 children.
		node.querySelectorAll<HTMLHeadingElement>('h1, h2, h3').forEach((heading) => {
			const { text, charCount } = collectSection(heading);

			// H1 and H2 are always treated as top-level sections and get a button unconditionally.
			// H3 only gets a button when its prose meets the minimum length.
			if (heading.tagName === 'H3' && charCount < MIN_SECTION_CHARS) return;

			attachButton(heading, 'md-copy-btn--section', 'Copy section', () => text);
		});

		// ── Bold-paragraph headings (Claude's **Title** + --- style) ─────────
		//
		// Only treat as a section title when immediately preceded by <hr> or
		// at the very start — this excludes mid-section sub-labels like
		// "Connection distances:" which appear inside another section's body.
		node.querySelectorAll<HTMLParagraphElement>('p').forEach((p) => {
			if (!isBoldHeading(p)) return;

			const prev = p.previousElementSibling;
			const isTopLevel = prev === null || prev.tagName === 'HR';
			if (!isTopLevel) return;

			const { text, charCount } = collectSection(p);
			if (charCount < MIN_SECTION_CHARS) return;

			// Append inside <strong> so the button sits right after the title text
			const anchor = (p.querySelector('strong') ?? p) as HTMLElement;
			attachButton(anchor, 'md-copy-btn--section', 'Copy section', () => text);
		});

	}

	// ── MutationObserver ─────────────────────────────────────────────────────
	//
	// subtree: false — only watch direct children of the markdown-preview node.
	// {@html} replaces direct children, so this catches real content changes.
	// subtree: true would also fire on our btn.innerHTML swaps (copy→check icon),
	// causing setup() to wipe the check icon immediately after clicking.
	const observer = new MutationObserver((mutations) => {
		if (setupPending) return;

		// Ignore mutations that are entirely from our own injected buttons
		const hasRealContentChange = mutations.some((m) =>
			Array.from(m.addedNodes).some(
				(n) => !(n instanceof Element && n.classList.contains('md-copy-btn'))
			)
		);

		if (hasRealContentChange) {
			setupPending = true;
			setTimeout(() => {
				setup();
				setupPending = false;
			}, 0);
		}
	});

	observer.observe(node, { childList: true, subtree: false });

	// Run immediately in case content is already present on mount
	if (node.children.length > 0) {
		setup();
	}

	return {
		update(_newContent?: string) {
			// No-op: MutationObserver re-runs setup() whenever {@html} replaces
			// the container's children, so we don't need to do anything here.
		},
		destroy() {
			observer.disconnect();
			node.querySelectorAll('.md-copy-btn').forEach((el) => el.remove());
		}
	};
}
