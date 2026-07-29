import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';
import { svelteTesting } from '@testing-library/svelte/vite';

export default defineConfig({
	plugins: [sveltekit(), tailwindcss(), svelteTesting()],
	server: {
		// Karma's declared port. strictPort makes a clash fail loudly instead of
		// silently moving to 5181+, which would leave the desktop launcher, the
		// API's CORS allowlist and the installed PWA all pointing at nothing.
		port: 5180,
		strictPort: true
	},
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		setupFiles: ['src/tests/setup.ts']
	}
});
