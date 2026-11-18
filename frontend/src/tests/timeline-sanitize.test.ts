import { describe, it, expect } from 'vitest';
import { sanitizeEventHtml } from '$lib/utils/sanitizeEventHtml';

function parse(html: string): HTMLElement {
	const el = document.createElement('div');
	el.innerHTML = sanitizeEventHtml(html);
	return el;
}

describe('sanitizeEventHtml', () => {
	it('removes inline styles but keeps the text and safe links', () => {
		const el = parse(
			'<div style="position:fixed;inset:0;z-index:9999">Session expired <a href="https://x.example/login">Sign in</a></div>'
		);
		expect(el.querySelector('[style]')).toBeNull();
		expect(el.textContent).toContain('Session expired');
		expect(el.querySelector('a')?.getAttribute('href')).toBe('https://x.example/login');
	});

	it('removes style and script elements', () => {
		const el = parse('<style>body{display:none}</style><script>alert(1)</script><p>ok</p>');
		expect(el.querySelector('style, script')).toBeNull();
		expect(el.textContent).toBe('ok');
	});

	it('turns a remote image into a plain link and never keeps the img', () => {
		const el = parse('<p><img src="https://evil.example/pixel.png" alt="chart"></p>');
		expect(el.querySelector('img')).toBeNull();
		const link = el.querySelector('a')!;
		expect(link.getAttribute('href')).toBe('https://evil.example/pixel.png');
		expect(link.textContent).toBe('Image: chart');
		expect(link.getAttribute('rel')).toContain('noopener');
	});

	it('keeps an inline data image', () => {
		const el = parse('<img src="data:image/png;base64,iVBORw0KGgo=" alt="shot">');
		expect(el.querySelector('img')?.getAttribute('src')).toMatch(/^data:image\/png/);
	});

	it('drops event handlers, srcset and other remote media', () => {
		const el = parse(
			'<img src="data:image/png;base64,AA==" srcset="https://evil.example/2x.png 2x" onerror="alert(1)">' +
				'<video src="https://evil.example/v.mp4"></video><svg><image href="https://evil.example/i.png"/></svg>'
		);
		expect(el.querySelector('[onerror], [srcset], video, svg, image')).toBeNull();
	});

	it('keeps what the markdown renderer writes, with task boxes as plain marks', () => {
		const html =
			'<h2>Plan</h2><ul><li><input disabled="" type="checkbox"> step</li>' +
			'<li><input checked="" disabled="" type="checkbox"> done</li></ul>' +
			'<pre><code class="language-ts">x = 1</code></pre>';
		const el = parse(html);
		expect(el.querySelector('h2')?.textContent).toBe('Plan');
		expect(el.querySelector('input')).toBeNull();
		expect(Array.from(el.querySelectorAll('li')).map((li) => li.textContent)).toEqual([
			'☐  step',
			'☑  done'
		]);
		const code = el.querySelector('pre code')!;
		expect(code.textContent).toBe('x = 1');
		expect(code.getAttribute('class')).toBe('language-ts');
	});

	it('does not let a body style itself with the app classes', () => {
		const el = parse(
			'<div class="fixed inset-0 z-50 bg-[var(--bg-base)]">cover</div>' +
				'<pre><code class="language-js fixed inset-0">y</code></pre><p class="language-x">p</p>'
		);
		expect(el.querySelector('div')?.hasAttribute('class')).toBe(false);
		expect(el.querySelector('code')?.getAttribute('class')).toBe('language-js');
		expect(el.querySelector('p')?.hasAttribute('class')).toBe(false);
		expect(el.textContent).toContain('cover');
	});

	it('removes forms and every control that could collect input', () => {
		const el = parse(
			'<form action="https://e.example/x" method="post"><input name="token" placeholder="Paste your API key">' +
				'<button formaction="https://e.example/y">Continue</button><select><option>a</option></select>' +
				'<textarea>t</textarea></form><dialog open>d</dialog><p>after</p>'
		);
		expect(el.querySelector('form, input, button, select, textarea, dialog')).toBeNull();
		expect(el.querySelector('[action], [formaction]')).toBeNull();
		expect(el.textContent).toContain('after');
	});

	it('drops ids, tab stops and popover wiring', () => {
		const el = parse(
			'<p id="timeline-end" tabindex="0" autofocus contenteditable="true">x</p>' +
				'<div popover id="p">pop</div><a href="https://x.example" popovertarget="p" accesskey="k">link</a>'
		);
		expect(
			el.querySelector(
				'[id], [tabindex], [autofocus], [contenteditable], [popover], [popovertarget], [accesskey]'
			)
		).toBeNull();
		expect(el.querySelector('a')?.getAttribute('href')).toBe('https://x.example');
	});
});
