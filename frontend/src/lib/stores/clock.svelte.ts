// Shared minute-resolution clock; one lazily started timer serves every reader.
const clock = $state({ now: new Date() });
let timer: ReturnType<typeof setInterval> | null = null;

export function getNow(): Date {
	if (timer === null && typeof window !== 'undefined') {
		timer = setInterval(() => {
			clock.now = new Date();
		}, 60_000);
	}
	return clock.now;
}
