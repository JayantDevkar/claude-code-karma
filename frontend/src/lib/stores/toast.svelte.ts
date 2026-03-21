/**
 * Minimal toast notification store using Svelte writable store.
 * Usage: import { toasts, addToast, dismissToast } from '$lib/stores/toast';
 */

import { writable, get } from 'svelte/store';

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
	id: number;
	message: string;
	type: ToastType;
}

let _id = 0;
const _toasts = writable<Toast[]>([]);

export const toasts = { subscribe: _toasts.subscribe };

export function addToast(message: string, type: ToastType = 'info', duration = 4000) {
	const id = ++_id;
	_toasts.update((t) => [...t, { id, message, type }]);

	if (duration > 0) {
		setTimeout(() => dismissToast(id), duration);
	}
}

export function dismissToast(id: number) {
	_toasts.update((t) => t.filter((toast) => toast.id !== id));
}
