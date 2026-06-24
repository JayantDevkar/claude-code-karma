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
