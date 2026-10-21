import process from 'node:process';
import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// The desktop launcher builds aside, then swaps the result into build/
		adapter: adapter({ out: process.env.KARMA_BUILD_OUT || 'build' })
	}
};

export default config;
