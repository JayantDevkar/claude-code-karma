import { readFileSync, statSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

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
