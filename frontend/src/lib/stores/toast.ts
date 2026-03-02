/**
 * Minimal toast notification store using Svelte 5 runes.
 * Usage: import { toasts, addToast, dismissToast } from '$lib/stores/toast';
 */

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
	id: number;
	message: string;
	type: ToastType;
}

let _id = 0;
let _toasts = $state<Toast[]>([]);

export const toasts = {
	get list() {
		return _toasts;
	}
};

export function addToast(message: string, type: ToastType = 'info', duration = 4000) {
	const id = ++_id;
	_toasts = [..._toasts, { id, message, type }];

	if (duration > 0) {
		setTimeout(() => dismissToast(id), duration);
	}
}

export function dismissToast(id: number) {
	_toasts = _toasts.filter((t) => t.id !== id);
}
