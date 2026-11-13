// Shared minute-resolution clock; one lazily started timer serves every reader.
const clock = $state({ now: new Date() });
let timer: ReturnType<typeof setInterval> | null = null;

export function getNow(): Date {
	if (typeof window === 'undefined') return new Date();
	if (timer === null) {
		timer = setInterval(() => {
			clock.now = new Date();
		}, 60_000);
	}
	return clock.now;
}
