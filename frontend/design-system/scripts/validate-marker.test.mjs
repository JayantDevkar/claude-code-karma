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
