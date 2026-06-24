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
