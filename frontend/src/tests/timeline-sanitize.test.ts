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

	it('keeps ordinary markdown output as it is', () => {
		const html =
			'<h2>Plan</h2><ul><li><input disabled="" type="checkbox"> step</li></ul><pre><code>x = 1</code></pre>';
		const el = parse(html);
		expect(el.querySelector('h2')?.textContent).toBe('Plan');
		expect(el.querySelector('input[type="checkbox"]')).not.toBeNull();
		expect(el.querySelector('pre code')?.textContent).toBe('x = 1');
	});
});
