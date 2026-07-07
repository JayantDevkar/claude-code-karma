# Claude Karma Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an in-repo, token-derived design-system catalog for Claude Karma and sync it to claude.ai/design, so UI/UX changes round-trip between code and Claude Design.

**Architecture:** Approach B from the spec — extract `app.css` tokens into a single-source `tokens.css` imported by both the app and the catalog; generate foundation cards from the tokens with a zero-dependency Node script; hand-author HTML previews for the 13 `ui/` primitives; link cards to source via `mapping.json`; sync the bundle with the `DesignSync` tool.

**Tech Stack:** SvelteKit 2 / Svelte 5, Tailwind CSS 4 (CSS `@theme`, no config), Node ESM (`"type":"module"`), `node:test` for script unit tests, framework-free static HTML for the catalog.

**Spec:** `docs/superpowers/specs/2026-06-23-claude-karma-design-system-design.md`

## Global Constraints

- All paths below are relative to repo root `/Users/jayantdevkar/Documents/GitHub/claude-karma` unless noted; npm scripts run with cwd = `frontend/`.
- Catalog previews are **framework-free static HTML** — no Svelte, no Vite, no `bits-ui`. They `<link>` `../shared/tokens.css` and `../shared/preview.css`.
- Every catalog `.html` file's **literal first line** is `<!-- @dsCard group="…" -->` — no BOM, no leading blank line. This is mandatory for the Claude Design render-check.
- Token extraction is **verbatim** — copy bytes, do not "tidy" the known dark-block inconsistencies (spec §5.1).
- Node scripts: pure Node built-ins only, **no new dependencies**. Resolve file paths relative to `import.meta.url`, not cwd.
- Generated/derived files are gitignored (`catalog/shared/tokens.css`, `catalog/foundations/`, `catalog/.render-check.json`); authored files are committed.
- Group labels (free-form): `Colors`, `Type`, `Spacing`, `Radius`, `Shadow`, `Motion`, `Focus`, `Brand`, `Components`.
- Branch: `feat/design-system`. Commit after every task.

---

### Task 1: Extract the token layer into `tokens.css`

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/app.css` (remove lines 12–539; add an `@import`)

**Interfaces:**
- Produces: `frontend/src/styles/tokens.css` containing the three token blocks (`:root`, `:root[data-theme='dark']`, `@media (prefers-color-scheme: dark)`). Consumed by the app (via `app.css`) and by `build-catalog.mjs` (copied into the bundle).

- [ ] **Step 1: Create `frontend/src/styles/tokens.css`** — copy `frontend/src/app.css` lines **12–539 verbatim** (the `:root {…}`, `:root[data-theme='dark'] {…}`, and `@media (prefers-color-scheme: dark) { :root:not([data-theme='light']) {…} }` blocks). Prepend one comment line:

```css
/* Claude Karma design tokens — single source of truth (imported by app.css + the design-system catalog) */
```

- [ ] **Step 2: Edit `frontend/src/app.css`** — delete the original lines 12–539 (the three token blocks, keeping the `@theme {}` block at lines 3–6 and `@import 'tailwindcss'` at line 1). Insert the token import immediately after the `@theme {}` block so order is `tailwindcss` → `@theme` → tokens → rest:

```css
@import 'tailwindcss';

@theme {
	--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
	--font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

@import './styles/tokens.css';

/* ============================================
   KEYBOARD ACCESSIBILITY - FOCUS SYSTEM
   ============================================ */
/* …existing focus rules continue unchanged… */
```

- [ ] **Step 3: Type-check** — Run: `cd frontend && npm run check`. Expected: completes with the same result as before this task (0 new errors).

- [ ] **Step 4: Production build** — Run: `cd frontend && npm run build`. Expected: build succeeds (adapter-node output, no CSS resolution errors).

- [ ] **Step 5: Visual parity check** — Run: `cd frontend && npm run dev` (background), open `http://localhost:5173`, confirm the app looks identical in light mode and after toggling dark mode (theme toggle in header). Stop the dev server. This is a pure extraction; any visual change means a copy error — fix before committing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app.css
git commit -m "refactor(frontend): extract design tokens into single-source tokens.css"
```

---

### Task 2: Catalog scaffold — `preview.css`, `mapping.json`, ignore rules

**Files:**
- Create: `frontend/design-system/catalog/shared/preview.css`
- Create: `frontend/design-system/catalog/mapping.json`
- Modify: `frontend/.prettierignore`, `frontend/.gitignore`, `frontend/eslint.config.js`

**Interfaces:**
- Produces: `preview.css` (reset + frame + state-attr styling + theme-toggle button) linked by every preview; `mapping.json` (21 entries: 8 foundations → `src/styles/tokens.css`, 13 components → their `.svelte` source(s)) consumed by `drift-check.mjs`.

- [ ] **Step 1: Create `frontend/design-system/catalog/shared/preview.css`:**

```css
/* Shared chrome for design-system preview cards (framework-free). */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
	margin: 0;
	font-family: var(--font-sans);
	background: var(--bg-base);
	color: var(--text-primary);
	font-variant-numeric: tabular-nums;
	padding: 24px;
}
.ds-frame { max-width: 980px; margin: 0 auto; }
.ds-title { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
.ds-subtitle { font-size: 13px; color: var(--text-muted); margin: 0 0 20px; }
.ds-section { margin: 24px 0; }
.ds-section-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); margin: 0 0 10px; }
.ds-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.ds-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.ds-swatch { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }
.ds-swatch__chip { height: 56px; }
.ds-swatch__meta { padding: 8px 10px; font-size: 11px; }
.ds-swatch__name { font-family: var(--font-mono); color: var(--text-primary); }
.ds-swatch__val { font-family: var(--font-mono); color: var(--text-muted); }
.ds-card { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 16px; background: var(--bg-subtle); }
/* Plain-CSS equivalents of the runtime state attributes bits-ui sets, so static previews can show both states */
[data-state='active'] { background: var(--bg-base); color: var(--text-primary); box-shadow: var(--shadow-sm); }
[data-state='inactive'] { color: var(--text-secondary); }
/* Theme toggle button (fixed) */
.ds-theme-toggle {
	position: fixed; bottom: 16px; right: 16px; z-index: 10;
	display: inline-flex; align-items: center; gap: 6px;
	padding: 6px 12px; font: inherit; font-size: 12px;
	border: 1px solid var(--border); border-radius: var(--radius-md);
	background: var(--bg-base); color: var(--text-secondary); cursor: pointer;
}
.ds-theme-toggle:hover { color: var(--text-primary); border-color: var(--border-hover); }
```

- [ ] **Step 2: Create `frontend/design-system/catalog/mapping.json`:**

```json
{
  "foundations/colors.html": ["src/styles/tokens.css"],
  "foundations/typography.html": ["src/styles/tokens.css"],
  "foundations/spacing.html": ["src/styles/tokens.css"],
  "foundations/radius.html": ["src/styles/tokens.css"],
  "foundations/shadow.html": ["src/styles/tokens.css"],
  "foundations/motion.html": ["src/styles/tokens.css"],
  "foundations/focus.html": ["src/styles/tokens.css"],
  "foundations/brand.html": ["src/styles/tokens.css"],
  "components/badge.html": ["src/lib/components/ui/Badge.svelte"],
  "components/card.html": ["src/lib/components/ui/Card.svelte"],
  "components/collapsible-group.html": ["src/lib/components/ui/CollapsibleGroup.svelte"],
  "components/empty-state.html": ["src/lib/components/ui/EmptyState.svelte"],
  "components/key-indicator.html": ["src/lib/components/ui/KeyIndicator.svelte"],
  "components/modal.html": ["src/lib/components/ui/Modal.svelte"],
  "components/segmented-control.html": ["src/lib/components/ui/SegmentedControl.svelte"],
  "components/select-dropdown.html": ["src/lib/components/ui/SelectDropdown.svelte"],
  "components/switch.html": ["src/lib/components/ui/Switch.svelte"],
  "components/tabs.html": ["src/lib/components/ui/Tabs.svelte", "src/lib/components/ui/TabsList.svelte", "src/lib/components/ui/TabsTrigger.svelte", "src/lib/components/ui/TabsContent.svelte"],
  "components/text-input.html": ["src/lib/components/ui/TextInput.svelte"],
  "components/theme-toggle.html": ["src/lib/components/ui/ThemeToggle.svelte"],
  "components/tier-badge.html": ["src/lib/components/ui/TierBadge.svelte"]
}
```

- [ ] **Step 3: Append to `frontend/.prettierignore`** (prevents Prettier moving the `@dsCard` marker off line 1):

```
design-system/catalog/**
```

- [ ] **Step 4: Append to `frontend/.gitignore`** (derived artifacts):

```
# design-system generated artifacts
design-system/catalog/shared/tokens.css
design-system/catalog/foundations/
design-system/catalog/.render-check.json
```

- [ ] **Step 5: Edit `frontend/eslint.config.js`** — add `'design-system/scripts/*.mjs'` to the existing `ignores` array (so the generator scripts aren't linted under the base JS config). If the file uses multiple config objects, add it to the global `ignores` block.

- [ ] **Step 6: Verify ignore rules** — Run: `cd frontend && npx prettier --check 'design-system/catalog/**' 2>&1 | head` (expected: "no files" / nothing matched, confirming the ignore). Run `git check-ignore design-system/catalog/foundations/x.html` (expected: prints the path, confirming it's ignored).

- [ ] **Step 7: Commit**

```bash
git add frontend/design-system/catalog/shared/preview.css frontend/design-system/catalog/mapping.json frontend/.prettierignore frontend/.gitignore frontend/eslint.config.js
git commit -m "chore(design-system): scaffold catalog shared assets + ignore rules"
```

---

### Task 3: `generate-foundations.mjs` (token parser + card emitter)

**Files:**
- Create: `frontend/design-system/scripts/generate-foundations.mjs`
- Test: `frontend/design-system/scripts/parse-tokens.test.mjs`

**Interfaces:**
- Produces (exported from `generate-foundations.mjs`): `parseTokens(css: string) => { light: Map<string,string>, dark: Map<string,string> }` and `generate(opts?: {tokensPath, outDir}) => string[]` (returns written file paths). Consumed by `build-catalog.mjs`.

- [ ] **Step 1: Write the failing parser test** — `frontend/design-system/scripts/parse-tokens.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTokens } from './generate-foundations.mjs';

const SAMPLE = `
:root {
	--accent: #7c3aed;
	--spacing-1: 4px;
}
:root[data-theme='dark'] {
	--accent: #a78bfa;
}
@media (prefers-color-scheme: dark) {
	:root:not([data-theme='light']) {
		--accent: #a78bfa;
	}
}
`;

test('parseTokens extracts light tokens', () => {
	const { light } = parseTokens(SAMPLE);
	assert.equal(light.get('--accent'), '#7c3aed');
	assert.equal(light.get('--spacing-1'), '4px');
});

test('parseTokens extracts dark overrides only from the data-theme block', () => {
	const { dark } = parseTokens(SAMPLE);
	assert.equal(dark.get('--accent'), '#a78bfa');
	assert.equal(dark.has('--spacing-1'), false);
});
```

- [ ] **Step 2: Run the test, verify it fails** — Run: `cd frontend && node --test design-system/scripts/parse-tokens.test.mjs`. Expected: FAIL (cannot import `parseTokens` / module not found).

- [ ] **Step 3: Implement `frontend/design-system/scripts/generate-foundations.mjs`** with the state-machine parser, prefix grouping, and HTML emitter. Path resolution via `import.meta.url`. Key contract: `parseTokens` returns two Maps; `generate()` writes 8 files to `outDir` (default `<frontend>/design-system/catalog/foundations`), each with a valid first-line `@dsCard` marker, each `<link>`ing `../shared/tokens.css` and `../shared/preview.css`, defaulting `<html data-theme="light">`, and including a theme-toggle button + inline toggle script. Implementation:

```js
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
```

- [ ] **Step 4: Run the parser test, verify it passes** — Run: `cd frontend && node --test design-system/scripts/parse-tokens.test.mjs`. Expected: PASS (2 tests).

- [ ] **Step 5: Smoke-run the generator** — Run: `cd frontend && node design-system/scripts/generate-foundations.mjs`. Expected: prints "generated 8 foundation cards"; `design-system/catalog/foundations/` now has 8 `.html` files. Spot-check `head -1 design-system/catalog/foundations/colors.html` → exactly `<!-- @dsCard group="Colors" -->`.

- [ ] **Step 6: Commit**

```bash
git add frontend/design-system/scripts/generate-foundations.mjs frontend/design-system/scripts/parse-tokens.test.mjs
git commit -m "feat(design-system): token parser + foundation card generator"
```

---

### Task 4: `build-catalog.mjs` + `drift-check.mjs` + npm scripts

**Files:**
- Create: `frontend/design-system/scripts/build-catalog.mjs`
- Create: `frontend/design-system/scripts/drift-check.mjs`
- Test: `frontend/design-system/scripts/validate-marker.test.mjs`
- Modify: `frontend/package.json` (add `ds:build`, `ds:drift`)

**Interfaces:**
- Consumes: `generate()` from `generate-foundations.mjs`; `mapping.json`.
- Produces (exported from `build-catalog.mjs`): `hasValidMarker(content: string) => boolean`. `build-catalog.mjs` run as CLI: copies tokens, generates foundations, validates every `catalog/**/*.html` first line, writes `.render-check.json`, exits non-zero on any invalid marker.

- [ ] **Step 1: Write the failing marker-validator test** — `frontend/design-system/scripts/validate-marker.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hasValidMarker } from './build-catalog.mjs';

test('accepts a valid first-line marker', () => {
	assert.equal(hasValidMarker('<!-- @dsCard group="Colors" -->\n<html></html>'), true);
});
test('rejects a marker not on the first line', () => {
	assert.equal(hasValidMarker('\n<!-- @dsCard group="Colors" -->'), false);
});
test('rejects a missing marker', () => {
	assert.equal(hasValidMarker('<html></html>'), false);
});
```

- [ ] **Step 2: Run the test, verify it fails** — Run: `cd frontend && node --test design-system/scripts/validate-marker.test.mjs`. Expected: FAIL (cannot import `hasValidMarker`).

- [ ] **Step 3: Implement `frontend/design-system/scripts/build-catalog.mjs`:**

```js
import { readFileSync, writeFileSync, copyFileSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, relative } from 'node:path';
import { generate } from './generate-foundations.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '..', '..');
const CATALOG = resolve(FRONTEND, 'design-system/catalog');
const MARKER_RE = /^<!--\s*@dsCard\s+group="[^"]+"\s*-->$/;

export function hasValidMarker(content) {
	const firstLine = content.split('\n')[0];
	return MARKER_RE.test(firstLine.trim()) && !firstLine.startsWith('﻿');
}

function walkHtml(dir, acc = []) {
	for (const e of readdirSync(dir, { withFileTypes: true })) {
		const p = resolve(dir, e.name);
		if (e.isDirectory()) walkHtml(p, acc);
		else if (e.name.endsWith('.html')) acc.push(p);
	}
	return acc;
}

function build() {
	mkdirSync(resolve(CATALOG, 'shared'), { recursive: true });
	copyFileSync(resolve(FRONTEND, 'src/styles/tokens.css'), resolve(CATALOG, 'shared/tokens.css'));
	generate();
	const files = walkHtml(CATALOG);
	const bad = files.filter((f) => !hasValidMarker(readFileSync(f, 'utf8')));
	writeFileSync(resolve(CATALOG, '.render-check.json'),
		JSON.stringify({ total: files.length, bad: bad.length, thin: 0, variantsIdentical: 0 }, null, 2));
	if (bad.length) {
		console.error('Invalid/missing @dsCard marker (must be literal first line):');
		for (const f of bad) console.error('  ' + relative(FRONTEND, f));
		process.exit(1);
	}
	console.log(`catalog OK — ${files.length} cards validated`);
}

if (import.meta.url === `file://${process.argv[1]}`) build();
```

- [ ] **Step 4: Run the marker test, verify it passes** — Run: `cd frontend && node --test design-system/scripts/validate-marker.test.mjs`. Expected: PASS (3 tests).

- [ ] **Step 5: Implement `frontend/design-system/scripts/drift-check.mjs`:**

```js
import { readFileSync, statSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, relative } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '..', '..');
const CATALOG = resolve(FRONTEND, 'design-system/catalog');

const mapping = JSON.parse(readFileSync(resolve(CATALOG, 'mapping.json'), 'utf8'));
const drift = [];
for (const [card, sources] of Object.entries(mapping)) {
	const cardPath = resolve(CATALOG, card);
	if (!existsSync(cardPath)) continue; // not yet authored / generated
	const cardM = statSync(cardPath).mtimeMs;
	for (const src of sources) {
		const sp = resolve(FRONTEND, src);
		if (existsSync(sp) && statSync(sp).mtimeMs > cardM) {
			drift.push(`${card}  ⟵  ${src} (source newer)`);
		}
	}
}
if (drift.length) {
	console.error('DRIFT — these cards are older than their mapped source(s):');
	for (const d of drift) console.error('  ' + d);
	process.exit(1);
}
console.log('no drift — all cards are current with their sources');
```

- [ ] **Step 6: Add npm scripts to `frontend/package.json`** — inside `"scripts"`:

```json
"ds:build": "node design-system/scripts/build-catalog.mjs",
"ds:drift": "node design-system/scripts/drift-check.mjs"
```

- [ ] **Step 7: Run the build** — Run: `cd frontend && npm run ds:build`. Expected: "catalog OK — 8 cards validated"; `catalog/shared/tokens.css` exists; `catalog/.render-check.json` shows `{total:8,bad:0,...}`.

- [ ] **Step 8: Browser-verify foundations** — open `frontend/design-system/catalog/foundations/colors.html` (and `spacing.html`, `shadow.html`) directly in a browser; confirm swatches/demos render and the "Toggle theme" button flips light/dark. Fix the generator if any card is blank or fails to toggle.

- [ ] **Step 9: Commit**

```bash
git add frontend/design-system/scripts/build-catalog.mjs frontend/design-system/scripts/drift-check.mjs frontend/design-system/scripts/validate-marker.test.mjs frontend/package.json
git commit -m "feat(design-system): build-catalog + drift-check + ds:build/ds:drift scripts"
```

---

### Task 5: Primitive previews — Group A (8 static cards)

Author one self-contained HTML preview per primitive under `frontend/design-system/catalog/components/`. **For each file: first read the primitive's `.svelte` source** to mirror its real props/variants, then write static HTML using shared tokens. Every file's literal first line is `<!-- @dsCard group="Components" -->`, links `../shared/tokens.css` + `../shared/preview.css`, defaults `<html data-theme="light">`, and includes the same `.ds-theme-toggle` button + inline toggle script used in the generator's `page()` template.

**Files (create all):** `key-indicator.html`, `badge.html`, `card.html`, `text-input.html`, `select-dropdown.html`, `empty-state.html`, `tier-badge.html`, `theme-toggle.html`

**Per-file authoring spec:**
- **badge.html** (`Badge.svelte`) — render all 10 variants (default, accent, success, warning, error, info, purple, blue, emerald, slate) × both sizes (sm, md), plus a row showing `rounded="full"`. ≥20 distinct badges. Pure CSS vars.
- **card.html** (`Card.svelte`) — 3 variants (default, subtle, interactive) × 4 paddings (none, sm, md, lg); give each real content so `interactive`'s hover reads.
- **key-indicator.html** (`KeyIndicator.svelte`) — replicate the `<kbd>` styling from the source; show `⌘K`, `⌥⇧P`, and a `G then T` chord sequence.
- **text-input.html** (`TextInput.svelte`) — native `<input>` styled with tokens; show default, placeholder, disabled, and `type="password"`; focus via `:focus` border/ring using `var(--accent)`.
- **select-dropdown.html** (`SelectDropdown.svelte`) — native `<select>` with `appearance:none` + inline ChevronDown SVG; default + disabled.
- **empty-state.html** (`EmptyState.svelte`) — 3 configs: icon-only, with action button, bare; use an inline SVG stand-in for `KarmaIcon`.
- **tier-badge.html** (`TierBadge.svelte`) — **read `src/lib/utils.ts` ~1210–1233 (`tierConfigs`) first** and inline the exact bg/iconColor hex/rgba per tier; render very-high, high, medium; add a note that `tier='low'` renders nothing by design.
- **theme-toggle.html** (`ThemeToggle.svelte`) — show the Sun and Moon icon states side by side, plus one live button that flips `data-theme` on `<html>` (mirrors the app behavior).

**Worked example — `frontend/design-system/catalog/components/badge.html` (use this exact pattern for the others):**

```html
<!-- @dsCard group="Components" -->
<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Badge</title>
<link rel="stylesheet" href="../shared/tokens.css">
<link rel="stylesheet" href="../shared/preview.css">
<style>
.badge { display:inline-flex; align-items:center; gap:4px; font-family:var(--font-sans); font-weight:500; border:1px solid transparent; }
.badge--sm { font-size:11px; padding:2px 8px; }
.badge--md { font-size:12px; padding:4px 10px; }
.badge--md\.rounded { border-radius:9999px; }
.badge.r-md { border-radius:var(--radius-md); }
.badge.r-full { border-radius:9999px; }
.v-default { background:var(--bg-muted); color:var(--text-secondary); border-color:var(--border); }
.v-accent { background:var(--accent-subtle); color:var(--accent); }
.v-success { background:var(--success-subtle); color:var(--success); }
.v-warning { background:var(--warning-subtle); color:var(--warning); }
.v-error { background:var(--error-subtle); color:var(--error); }
.v-info { background:var(--info-subtle); color:var(--info); }
.v-purple { background:var(--accent-subtle); color:var(--accent); }
.v-blue { background:var(--info-subtle); color:var(--info); }
.v-emerald { background:var(--success-subtle); color:var(--success); }
.v-slate { background:var(--bg-muted); color:var(--text-muted); }
</style>
</head>
<body>
<div class="ds-frame">
<h1 class="ds-title">Badge</h1>
<p class="ds-subtitle">10 variants × 2 sizes — src/lib/components/ui/Badge.svelte</p>
<div class="ds-section"><p class="ds-section-label">Size md</p><div class="ds-row">
<span class="badge badge--md r-md v-default">default</span>
<span class="badge badge--md r-md v-accent">accent</span>
<span class="badge badge--md r-md v-success">success</span>
<span class="badge badge--md r-md v-warning">warning</span>
<span class="badge badge--md r-md v-error">error</span>
<span class="badge badge--md r-md v-info">info</span>
<span class="badge badge--md r-md v-purple">purple</span>
<span class="badge badge--md r-md v-blue">blue</span>
<span class="badge badge--md r-md v-emerald">emerald</span>
<span class="badge badge--md r-md v-slate">slate</span>
</div></div>
<div class="ds-section"><p class="ds-section-label">Size sm</p><div class="ds-row">
<span class="badge badge--sm r-md v-default">default</span>
<span class="badge badge--sm r-md v-accent">accent</span>
<span class="badge badge--sm r-md v-success">success</span>
<span class="badge badge--sm r-md v-warning">warning</span>
<span class="badge badge--sm r-md v-error">error</span>
<span class="badge badge--sm r-md v-info">info</span>
</div></div>
<div class="ds-section"><p class="ds-section-label">Rounded full</p><div class="ds-row">
<span class="badge badge--md r-full v-accent">accent</span>
<span class="badge badge--md r-full v-success">success</span>
<span class="badge badge--md r-full v-info">info</span>
</div></div>
</div>
<button class="ds-theme-toggle" onclick="(function(r){var d=r.getAttribute('data-theme')==='dark';r.setAttribute('data-theme',d?'light':'dark');})(document.documentElement)">Toggle theme</button>
</body>
</html>
```

> Note: variant→token mapping above is the documented intent; while authoring, open `Badge.svelte` and match its actual class/variant logic. If a variant maps to a token not shown here, use the source's mapping.

- [ ] **Step 1:** Author `key-indicator.html` (simplest), then `badge.html` (pattern above), `card.html`, `text-input.html`, `select-dropdown.html`, `empty-state.html`, `tier-badge.html` (read utils.ts first), `theme-toggle.html`.
- [ ] **Step 2: Validate** — Run: `cd frontend && npm run ds:build`. Expected: "catalog OK — 16 cards validated" (8 foundations + 8 group-A). Fix any file the validator lists.
- [ ] **Step 3: Browser spot-check** — open `badge.html`, `tier-badge.html`, `empty-state.html`; confirm variants render and the theme toggle works.
- [ ] **Step 4: Commit**

```bash
git add frontend/design-system/catalog/components/
git commit -m "feat(design-system): static primitive previews (badge, card, key-indicator, text-input, select, empty-state, tier-badge, theme-toggle)"
```

---

### Task 6: Primitive previews — Group B (5 interactive cards)

Same conventions as Task 5. These four use `bits-ui` at runtime, so replicate the rendered DOM and **hardcode the state attributes** the library sets.

**Files (create all):** `segmented-control.html`, `switch.html`, `tabs.html`, `collapsible-group.html`, `modal.html`

**Per-file authoring spec:**
- **segmented-control.html** (`SegmentedControl.svelte`) — 2 sizes (sm, md); examples with 2, 3, and 4 options; mark one option active via `aria-checked="true"` (style `[aria-checked='true']{background:var(--accent);color:#fff}` in a local `<style>`); include a disabled example. Optional small JS to flip active on click.
- **switch.html** (`Switch.svelte`) — `<button role="switch">` track + `<span>` thumb; show all 4 states (checked/unchecked × enabled/disabled) using `data-state="checked|unchecked"`; checked uses `background:var(--accent)`; focus ring uses `var(--accent)`.
- **tabs.html** (`Tabs/TabsList/TabsTrigger/TabsContent`) — `role="tablist"` with `<button role="tab" data-state="active|inactive">` (preview.css already styles `[data-state]`); one tab active, others inactive; show a `role="tabpanel"`; include a with-icon trigger variant; optional JS to switch tabs.
- **collapsible-group.html** (`CollapsibleGroup.svelte`) — show an expanded and a collapsed instance side by side (no Svelte transition); include the accent-border variant (`border-left:3px solid var(--accent)`); rotate the chevron via CSS transform on the open one.
- **modal.html** (`Modal.svelte`) — static overlay (`position:fixed;inset:0;background:rgba(0,0,0,.5)`) + centered content box (`role="dialog"`); inline the `@keyframes` from the component's local `<style>`; show all 4 `maxWidth` sizes (sm/md/lg/xl) as separate boxes or via a size switcher; a button toggles `display` to open/close one instance.

- [ ] **Step 1:** Author all 5 files, reading each `.svelte` source first.
- [ ] **Step 2: Validate** — Run: `cd frontend && npm run ds:build`. Expected: "catalog OK — 21 cards validated" (8 + 13).
- [ ] **Step 3: Browser spot-check** — open `switch.html`, `tabs.html`, `modal.html`; confirm both states are visible and interactions (where JS added) work; toggle theme.
- [ ] **Step 4: Commit**

```bash
git add frontend/design-system/catalog/components/
git commit -m "feat(design-system): interactive primitive previews (segmented-control, switch, tabs, collapsible-group, modal)"
```

---

### Task 7: Integration check + design-system README

**Files:**
- Create: `frontend/design-system/README.md`

**Interfaces:** none new — verifies the whole pipeline.

- [ ] **Step 1: Full build** — Run: `cd frontend && npm run ds:build`. Expected: "catalog OK — 21 cards validated", `.render-check.json` shows `{total:21,bad:0,...}`.
- [ ] **Step 2: Drift check** — Run: `cd frontend && npm run ds:drift`. Expected: "no drift …". (Authoring just now made previews newer than sources.)
- [ ] **Step 3: Lint/format guards still pass** — Run: `cd frontend && npm run check`. Expected: passes (catalog HTML not type-checked; scripts ignored by eslint).
- [ ] **Step 4: Script unit tests** — Run: `cd frontend && node --test design-system/scripts/*.test.mjs`. Expected: all PASS.
- [ ] **Step 5: Write `frontend/design-system/README.md`** documenting: what the catalog is, `npm run ds:build` / `ds:drift`, the `mapping.json` round-trip contract, that `shared/tokens.css` + `foundations/` are generated (gitignored), how to add a new primitive card, and how to sync to claude.ai/design (Task 8).
- [ ] **Step 6: Commit**

```bash
git add frontend/design-system/README.md
git commit -m "docs(design-system): catalog README + round-trip usage"
```

---

### Task 8: Sync to claude.ai/design (requires the user's claude.ai grant)

> **This is the only task with an external side effect.** The first `DesignSync` call prompts the user to grant design-system access to their claude.ai login, and it creates a project on their account. Do NOT run it without the user's go-ahead at execution time.

**Interfaces:** uses the `DesignSync` tool methods; `localDir = frontend/design-system/catalog`.

- [ ] **Step 1: Fresh build** — Run: `cd frontend && npm run ds:build`. Expected: 21 cards validated (bundle complete on disk).
- [ ] **Step 2: List/verify target** — `DesignSync({method:'list_projects'})`. If a "Claude Karma Design System" project exists, note its `projectId`; else `DesignSync({method:'create_project', name:'Claude Karma Design System'})` and capture the new `projectId`. Confirm `type === PROJECT_TYPE_DESIGN_SYSTEM` via `get_project`.
- [ ] **Step 3: Diff** — `DesignSync({method:'list_files', projectId})`; compute the write set = all files under `catalog/` (foundations/*.html, components/*.html, shared/tokens.css, shared/preview.css, mapping.json, .render-check.json).
- [ ] **Step 4: Finalize plan** — `DesignSync({method:'finalize_plan', projectId, writes:['**/*.html','shared/*.css','*.json'], localDir:'<abs>/frontend/design-system/catalog'})`. Capture `planId`.
- [ ] **Step 5: Write** — `DesignSync({method:'write_files', projectId, planId, files:[{path, localPath} …]})` (split into ≤256-file calls; here ~25 files in one call). Each file uses `localPath` so contents stream from disk.
- [ ] **Step 6: Verify** — `DesignSync({method:'list_files', projectId})` shows all cards; open claude.ai/design → the project's Design System pane → confirm cards appear grouped (Colors/Type/Spacing/…/Components) and the render-check passes.
- [ ] **Step 7:** No commit (remote-only). Record the `projectId` in `frontend/design-system/README.md` for future incremental syncs.

---

## Self-Review

**Spec coverage:** §5.1 token extraction → Task 1. §5.2 layout + git strategy → Tasks 2,4 (+ .gitignore). §5.3 generated foundations (parser, groups, plugin/data/spacing exceptions) → Task 3. §5.4 primitive previews + mapping + per-primitive notes → Tasks 2,5,6. §5.5 sync → Task 8. §5.6 round-trip (ds:drift) → Tasks 4,7. §5.7 build hygiene (prettierignore/gitignore/eslint, marker-on-line-1) → Tasks 2,4. §8 success criteria → Task 7 checks. All covered.

**Placeholder scan:** Foundation card HTML is fully generated by inlined code (Task 3). Primitive previews give a complete worked example (badge.html) + exact per-file specs + a "read the source first" instruction — this is deliberate (faithfully reproducing 13 components requires reading each source; inlining 13 final HTML files would be larger and less accurate). No "TBD"/"handle edge cases"/"similar to" placeholders remain.

**Type consistency:** `parseTokens` → `{light,dark}` Maps (Task 3) consumed by `generate()` (Task 3) and `hasValidMarker` (Task 4) used by its own test (Task 4). `mapping.json` keys (Task 2) consumed by `drift-check.mjs` (Task 4). Card counts are consistent: 8 → 16 → 21 across Tasks 4/5/6.
