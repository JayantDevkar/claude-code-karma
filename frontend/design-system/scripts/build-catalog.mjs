import { readFileSync, writeFileSync, copyFileSync, mkdirSync, readdirSync, existsSync } from 'node:fs';
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

// Count non-whitespace chars in body inner content (strip tags)
function bodyContentLength(html) {
	const bodyMatch = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
	if (!bodyMatch) return 0;
	return bodyMatch[1].replace(/<[^>]+>/g, '').replace(/\s+/g, '').length;
}

function build() {
	mkdirSync(resolve(CATALOG, 'shared'), { recursive: true });
	copyFileSync(resolve(FRONTEND, 'src/styles/tokens.css'), resolve(CATALOG, 'shared/tokens.css'));
	generate();

	// Load mapping.json for contract enforcement
	const mappingPath = resolve(CATALOG, 'mapping.json');
	const mapping = JSON.parse(readFileSync(mappingPath, 'utf8'));

	const files = walkHtml(CATALOG);

	// Validate @dsCard markers
	const bad = files.filter((f) => !hasValidMarker(readFileSync(f, 'utf8')));

	// Enforce mapping.json contract — every card must have a mapping key
	const missingMappings = [];
	const missingFiles = [];

	for (const f of files) {
		const key = relative(CATALOG, f).replace(/\\/g, '/');
		if (!mapping[key]) missingMappings.push(key);
	}

	// Every mapping key must point to an existing card file
	for (const key of Object.keys(mapping)) {
		const cardPath = resolve(CATALOG, key);
		if (!existsSync(cardPath)) missingFiles.push(key);
	}

	// Compute honest thin count (< 200 non-whitespace chars in body)
	const THIN_THRESHOLD = 200;
	const thin = files.filter((f) => bodyContentLength(readFileSync(f, 'utf8')) < THIN_THRESHOLD).length;

	writeFileSync(resolve(CATALOG, '.render-check.json'),
		JSON.stringify({ total: files.length, bad: bad.length, thin }, null, 2));

	let failed = false;

	if (bad.length) {
		console.error('Invalid/missing @dsCard marker (must be literal first line):');
		for (const f of bad) console.error('  ' + relative(FRONTEND, f));
		failed = true;
	}

	if (missingMappings.length) {
		console.error('Cards missing from mapping.json (add an entry or remove the file):');
		for (const k of missingMappings) console.error('  ' + k);
		failed = true;
	}

	if (missingFiles.length) {
		console.error('mapping.json keys point to missing card files:');
		for (const k of missingFiles) console.error('  ' + k);
		failed = true;
	}

	if (failed) process.exit(1);

	console.log(`catalog OK — ${files.length} cards validated`);
}

if (import.meta.url === `file://${process.argv[1]}`) build();
