import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';
import { svelteTesting } from '@testing-library/svelte/vite';

// Domains Karma is reachable under from behind a reverse proxy, comma-separated:
//   KARMA_ALLOWED_HOSTS=karma.example,karma.lan
// Empty leaves Vite's default, which still allows localhost and bare IPs.
const allowedHosts = (process.env.KARMA_ALLOWED_HOSTS ?? '')
	.split(',')
	.map((host) => host.trim())
	.filter(Boolean);

// Where the browser-facing proxy forwards to. The API runs in the same container.
const apiTarget = process.env.KARMA_API_TARGET || 'http://localhost:8020';

export default defineConfig({
	plugins: [sveltekit(), tailwindcss(), svelteTesting()],
	server: {
		// Karma's declared port. strictPort makes a clash fail loudly instead of
		// silently moving to 5181+, which would leave the desktop launcher, the
		// API's CORS allowlist and the installed PWA all pointing at nothing.
		port: 5180,
		strictPort: true,
		// Vite rejects requests whose Host header it doesn't know, so a reverse
		// proxy forwarding Host: $host would otherwise get a 403.
		allowedHosts,
		// Browser-side API calls go through the same origin as the page, so they
		// keep working over HTTPS and from machines other than the Karma host.
		// /api is already a SvelteKit route, hence /backend.
		proxy: {
			'/backend': {
				target: apiTarget,
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/backend/, '')
			}
		}
	},
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		setupFiles: ['src/tests/setup.ts']
	}
});
