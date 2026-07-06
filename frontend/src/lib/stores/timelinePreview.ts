import { writable } from 'svelte/store';

export interface PreviewLine {
	text: string;
	type: 'normal' | 'add' | 'remove';
}

export interface PreviewState {
	visible: boolean;
	x: number;
	y: number;
	title: string;
	lines: PreviewLine[];
}

function createPreviewStore() {
	const { subscribe, set, update } = writable<PreviewState>({
		visible: false,
		x: 0,
		y: 0,
		title: '',
		lines: []
	});

	let timer: ReturnType<typeof setTimeout> | null = null;

	return {
		subscribe,
		show(x: number, y: number, title: string, lines: PreviewLine[], delay = 350) {
			if (timer) clearTimeout(timer);
			timer = setTimeout(() => {
				set({ visible: true, x, y, title, lines });
			}, delay);
		},
		hide() {
			if (timer) {
				clearTimeout(timer);
				timer = null;
			}
			update((s) => ({ ...s, visible: false }));
		}
	};
}

export const timelinePreview = createPreviewStore();
