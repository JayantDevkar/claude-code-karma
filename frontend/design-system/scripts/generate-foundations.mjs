import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '..', '..');           // .../frontend
const TOKENS = resolve(FRONTEND, 'src/styles/tokens.css');
const OUT = resolve(FRONTEND, 'design-system/catalog/foundations');

const TOKEN_RE = /^\s*(--[\w-]+)\s*:\s*([^;]+?)\s*;/;

export function parseTokens(css) {
	const lines = css.split('\n');
	const light = new Map(), dark = new Map();
	let state = 'OUT', depth = 0;
	for (const line of lines) {
		const t = line.trim();
		if (state === 'OUT') {
			if (/^:root\[data-theme='dark'\]/.test(t)) { state = 'DARK'; depth = 1; continue; }
			if (/^:root\s*\{/.test(t)) { state = 'LIGHT'; depth = 1; continue; }
			// ignore @media / nested :root:not — we only read the explicit dark block
			continue;
		}
		const opens = (line.match(/\{/g) || []).length;
		const closes = (line.match(/\}/g) || []).length;
		const m = TOKEN_RE.exec(line);
		if (m) (state === 'LIGHT' ? light : dark).set(m[1], m[2]);
		depth += opens - closes;
		if (depth <= 0) state = 'OUT';
	}
	return { light, dark };
}

const isColor = (v) => /#|rgb|hsl|oklch|var\(/.test(v);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function page(group, title, subtitle, bodyHtml) {
	return `<!-- @dsCard group="${group}" -->
<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<link rel="stylesheet" href="../shared/tokens.css">
<link rel="stylesheet" href="../shared/preview.css">
</head>
<body>
<div class="ds-frame">
<h1 class="ds-title">${esc(title)}</h1>
<p class="ds-subtitle">${esc(subtitle)}</p>
${bodyHtml}
</div>
<button class="ds-theme-toggle" onclick="(function(r){var d=r.getAttribute('data-theme')==='dark';r.setAttribute('data-theme',d?'light':'dark');})(document.documentElement)">Toggle theme</button>
</body>
</html>
`;
}

function swatchGrid(entries) {
	const cells = entries.map(([name, val]) =>
		`<div class="ds-swatch"><div class="ds-swatch__chip" style="background:${val}"></div>` +
		`<div class="ds-swatch__meta"><div class="ds-swatch__name">${esc(name)}</div>` +
		`<div class="ds-swatch__val">${esc(val)}</div></div></div>`).join('\n');
	return `<div class="ds-grid">${cells}</div>`;
}

function byPrefix(light, predicate) {
	return [...light.entries()].filter(([n, v]) => predicate(n, v));
}

export function generate({ tokensPath = TOKENS, outDir = OUT } = {}) {
	const css = readFileSync(tokensPath, 'utf8');
	const { light } = parseTokens(css);
	mkdirSync(outDir, { recursive: true });
	const written = [];
	const write = (file, html) => { const p = resolve(outDir, file); writeFileSync(p, html); written.push(p); };

	// Colors — core + semantic + domain + nav + live-status, all color-valued tokens
	const colorEntries = byPrefix(light, (n, v) => isColor(v) && !n.startsWith('--plugin') && !n.startsWith('--data') && !n.startsWith('--font'));
	const aliasEntries = byPrefix(light, (n, v) => n.startsWith('--data'));
	const aliasNote = aliasEntries.length
		? `<div class="ds-section"><p class="ds-section-label">Aliases</p><div class="ds-card">` +
			aliasEntries.map(([n, v]) => `<div class="ds-swatch__name">${esc(n)} → ${esc(v)}</div>`).join('') + `</div></div>`
		: '';
	const pluginNote = `<div class="ds-section"><p class="ds-section-label">Computed at runtime</p><div class="ds-card">--plugin-* are OKLCH parameters consumed by JS (memoryTypeBadge.ts); not rendered as swatches.</div></div>`;
	write('colors.html', page('Colors', 'Colors', `${colorEntries.length} color tokens (toggle theme to compare)`, swatchGrid(colorEntries) + aliasNote + pluginNote));

	// Typography
	const fonts = byPrefix(light, (n) => n.startsWith('--font'));
	const typeBody = fonts.map(([n, v]) => `<div class="ds-section"><p class="ds-section-label">${esc(n)}</p>` +
		`<div style="font-family:${v};font-size:28px">The quick brown fox — 0123456789</div>` +
		`<div style="font-family:${v};font-size:14px;color:var(--text-secondary)">${esc(v)}</div></div>`).join('');
	write('typography.html', page('Type', 'Typography', 'Font families and a representative scale', typeBody +
		['32px','24px','18px','16px','14px','12px'].map(s => `<div style="font-size:${s}">Aa ${s}</div>`).join('')));

	// Spacing
	const spacing = byPrefix(light, (n) => n.startsWith('--spacing'));
	write('spacing.html', page('Spacing', 'Spacing', `${spacing.length} steps on a 4px grid`,
		spacing.map(([n, v]) => `<div class="ds-section"><p class="ds-section-label">${esc(n)} = ${esc(v)}</p>` +
			`<div style="height:16px;width:${v};background:var(--accent);border-radius:2px"></div></div>`).join('')));

	// Radius
	const radius = byPrefix(light, (n) => n.startsWith('--radius'));
	write('radius.html', page('Radius', 'Border Radius', `${radius.length} radii`,
		`<div class="ds-row">` + radius.map(([n, v]) => `<div style="text-align:center"><div style="width:80px;height:80px;background:var(--accent-subtle);border:1px solid var(--accent);border-radius:${v}"></div><div class="ds-swatch__name">${esc(n)}</div><div class="ds-swatch__val">${esc(v)}</div></div>`).join('') + `</div>`));

	// Shadow
	const shadow = byPrefix(light, (n) => n.startsWith('--shadow'));
	write('shadow.html', page('Shadow', 'Shadows', `${shadow.length} elevations`,
		`<div class="ds-row" style="gap:32px">` + shadow.map(([n]) => `<div style="text-align:center"><div style="width:120px;height:80px;background:var(--bg-base);border-radius:var(--radius-md);box-shadow:var(${n})"></div><div class="ds-swatch__name">${esc(n)}</div></div>`).join('') + `</div>`));

	// Motion
	const motion = byPrefix(light, (n) => n.startsWith('--duration') || n.startsWith('--ease'));
	write('motion.html', page('Motion', 'Motion', `${motion.length} timing tokens`,
		`<div class="ds-card">` + motion.map(([n, v]) => `<div class="ds-swatch__name">${esc(n)} = ${esc(v)}</div>`).join('') + `</div>`));

	// Focus
	write('focus.html', page('Focus', 'Focus Ring', 'Keyboard-accessibility focus system',
		`<div class="ds-row"><button style="padding:8px 16px;border-radius:var(--radius-md);border:1px solid var(--border);background:var(--bg-base);color:var(--text-primary);box-shadow:0 0 0 var(--focus-ring-offset) var(--bg-base),0 0 0 calc(var(--focus-ring-offset) + var(--focus-ring-width)) var(--focus-ring-color)">Focused button</button><span class="ds-swatch__val">--focus-ring-width / --focus-ring-offset / --focus-ring-color</span></div>`));

	// Brand
	write('brand.html', page('Brand', 'Brand', 'Accent identity and gradient',
		`<div class="ds-section"><div class="ds-swatch" style="max-width:240px"><div class="ds-swatch__chip" style="height:96px;background:var(--accent)"></div><div class="ds-swatch__meta"><div class="ds-swatch__name">--accent</div></div></div></div>` +
		`<div style="font-size:40px;font-weight:700;background:linear-gradient(135deg,var(--accent) 0%,#a78bfa 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">Claude Karma</div>`));

	return written;
}

// CLI entry
if (import.meta.url === `file://${process.argv[1]}`) {
	const files = generate();
	console.log(`generated ${files.length} foundation cards`);
}
