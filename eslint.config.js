import js from '@eslint/js';
import ts from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import svelte from 'eslint-plugin-svelte';
import svelteParser from 'svelte-eslint-parser';
import prettier from 'eslint-config-prettier';

/** Browser + Svelte 5 rune globals shared across all file types */
const browserGlobals = {
	// Browser APIs
	console: 'readonly',
	fetch: 'readonly',
	window: 'readonly',
	document: 'readonly',
	setTimeout: 'readonly',
	clearTimeout: 'readonly',
	setInterval: 'readonly',
	clearInterval: 'readonly',
	navigator: 'readonly',
	localStorage: 'readonly',
	sessionStorage: 'readonly',
	URL: 'readonly',
	URLSearchParams: 'readonly',
	RequestInit: 'readonly',
	Response: 'readonly',
	HTMLElement: 'readonly',
	HTMLInputElement: 'readonly',
	HTMLTextAreaElement: 'readonly',
	HTMLSelectElement: 'readonly',
	HTMLButtonElement: 'readonly',
	HTMLDivElement: 'readonly',
	HTMLAnchorElement: 'readonly',
	Element: 'readonly',
	Event: 'readonly',
	KeyboardEvent: 'readonly',
	MouseEvent: 'readonly',
	FocusEvent: 'readonly',
	CustomEvent: 'readonly',
	IntersectionObserver: 'readonly',
	MutationObserver: 'readonly',
	ResizeObserver: 'readonly',
	AbortController: 'readonly',
	requestAnimationFrame: 'readonly',
	cancelAnimationFrame: 'readonly',
	queueMicrotask: 'readonly',
	structuredClone: 'readonly',
	crypto: 'readonly',
	performance: 'readonly',
	ClipboardEvent: 'readonly',
	getComputedStyle: 'readonly',
	Map: 'readonly',
	Set: 'readonly',
	Promise: 'readonly',
	Blob: 'readonly',
	File: 'readonly',
	FormData: 'readonly',
	Headers: 'readonly',
	Request: 'readonly',
	DOMParser: 'readonly'
};

/** Svelte 5 runes — needed in .svelte and .svelte.ts files */
const svelteRuneGlobals = {
	$state: 'readonly',
	$derived: 'readonly',
	$effect: 'readonly',
	$props: 'readonly',
	$bindable: 'readonly',
	$inspect: 'readonly',
	$host: 'readonly'
};

export default [
	js.configs.recommended,
	{
		files: ['**/*.ts', '**/*.tsx'],
		ignores: ['**/*.svelte.ts', '**/*.d.ts'],
		plugins: {
			'@typescript-eslint': ts
		},
		languageOptions: {
			parser: tsParser,
			parserOptions: {
				project: './tsconfig.json',
				extraFileExtensions: ['.svelte']
			},
			globals: browserGlobals
		},
		rules: {
			...ts.configs.recommended.rules,
			'@typescript-eslint/no-unused-vars': [
				'warn',
				{
					argsIgnorePattern: '^_',
					varsIgnorePattern: '^_'
				}
			],
			'no-unused-vars': 'off'
		}
	},
	{
		files: ['**/*.svelte.ts'],
		plugins: {
			'@typescript-eslint': ts
		},
		languageOptions: {
			parser: tsParser,
			parserOptions: {
				project: './tsconfig.json',
				extraFileExtensions: ['.svelte']
			},
			globals: { ...browserGlobals, ...svelteRuneGlobals }
		},
		rules: {
			...ts.configs.recommended.rules,
			'@typescript-eslint/no-unused-vars': [
				'warn',
				{
					argsIgnorePattern: '^_',
					varsIgnorePattern: '^_'
				}
			],
			'no-unused-vars': 'off'
		}
	},
	{
		files: ['**/*.svelte'],
		plugins: {
			svelte,
			'@typescript-eslint': ts
		},
		languageOptions: {
			parser: svelteParser,
			parserOptions: {
				parser: tsParser,
				project: './tsconfig.json',
				extraFileExtensions: ['.svelte']
			},
			globals: { ...browserGlobals, ...svelteRuneGlobals }
		},
		rules: {
			...svelte.configs.recommended.rules,
			'no-unused-vars': 'off'
		}
	},
	prettier,
	{
		ignores: [
			'.svelte-kit/**',
			'build/**',
			'node_modules/**',
			'package/**',
			'.env',
			'.env.*',
			'!.env.example',
			'pnpm-lock.yaml',
			'package-lock.json',
			'yarn.lock',
			'**/*.d.ts'
		]
	}
];
