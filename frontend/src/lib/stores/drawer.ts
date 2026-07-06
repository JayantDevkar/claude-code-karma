import { writable } from 'svelte/store';
import type { TimelineEvent } from '$lib/api-types';

export type DrawerPayload =
	| { kind: 'shell'; event: TimelineEvent; sessionUuid: string; encodedName: string }
	| { kind: 'agent'; agentId: string; agentType: string | null; parentSessionUuid: string; encodedName: string }
	| { kind: 'diff'; path: string; oldString: string; newString: string }
	| { kind: 'file-read'; path: string; content: string }
	| null;

export const drawerStore = writable<DrawerPayload>(null);

export function openShellDrawer(event: TimelineEvent, sessionUuid: string, encodedName: string) {
	drawerStore.set({ kind: 'shell', event, sessionUuid, encodedName });
}

export function openAgentDrawer(agentId: string, agentType: string | null, parentSessionUuid: string, encodedName: string) {
	drawerStore.set({ kind: 'agent', agentId, agentType, parentSessionUuid, encodedName });
}

export function openDiffDrawer(path: string, oldString: string, newString: string) {
	drawerStore.set({ kind: 'diff', path, oldString, newString });
}

export function openFileReadDrawer(path: string, content: string) {
	drawerStore.set({ kind: 'file-read', path, content });
}

export function closeDrawer() {
	drawerStore.set(null);
}
