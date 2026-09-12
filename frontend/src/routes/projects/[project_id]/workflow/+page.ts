// The workflow board is a client-only canvas (Svelte Flow needs the DOM).
// Skip SSR for this route so there's no server render of the flow.
export const ssr = false;
