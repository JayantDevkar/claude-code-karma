/** Loading a tab whose data comes from the index, which answers 503 while it rebuilds. */

export const INDEX_REBUILDING_MESSAGE =
	'The index is rebuilding. This tab will load when it finishes.';

export const INDEX_STILL_REBUILDING_MESSAGE =
	'The index is still rebuilding. It is taking longer than usual.';

const DEFAULT_RETRY_SECONDS = 5;
const MIN_RETRY_SECONDS = 1;
const MAX_RETRY_SECONDS = 30;
const BACKOFF_FACTOR = 1.5;
/** Give up waiting after this long and offer a manual retry instead. */
export const MAX_WAIT_MS = 3 * 60 * 1000;

/** The wait for the index ran past MAX_WAIT_MS; the tab offers "Try again". */
export class IndexStillRebuildingError extends Error {
	constructor() {
		super(INDEX_STILL_REBUILDING_MESSAGE);
		this.name = 'IndexStillRebuildingError';
	}
}

function abortError(): DOMException {
	return new DOMException('Aborted', 'AbortError');
}

/** Seconds the server asked for, floored and capped; 5 when the header cannot be read. */
export function retryAfterSeconds(res: Response): number {
	const seconds = Number(res.headers.get('Retry-After'));
	const asked = Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_RETRY_SECONDS;
	return Math.min(Math.max(asked, MIN_RETRY_SECONDS), MAX_RETRY_SECONDS);
}

/** Delay before try number `attempt` (0-based): the asked delay, growing by half each time. */
export function retryDelayMs(res: Response, attempt = 0): number {
	const seconds = retryAfterSeconds(res) * Math.pow(BACKOFF_FACTOR, attempt);
	return Math.round(Math.min(seconds, MAX_RETRY_SECONDS) * 1000);
}

async function readDetail(res: Response): Promise<string | null> {
	try {
		const body = (await res.clone().json()) as { detail?: unknown };
		return typeof body.detail === 'string' ? body.detail : null;
	} catch {
		return null;
	}
}

/** True only for the API's "index is rebuilding" answer; any other 503 is a plain failure. */
export async function isIndexRebuilding(res: Response): Promise<boolean> {
	if (res.status !== 503) return false;
	const detail = await readDetail(res);
	return detail !== null && /index is rebuilding/i.test(detail);
}

export interface FetchWhenIndexedOptions {
	/** Called with true when the first 503 arrives and false once the wait ends */
	onRebuilding?: (rebuilding: boolean) => void;
	/** Abort to stop retrying, e.g. when the tab is hidden or its component destroyed */
	signal?: AbortSignal;
	fetchFn?: typeof fetch;
	/** Longest total wait before giving up with IndexStillRebuildingError */
	maxWaitMs?: number;
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
	return new Promise((resolve, reject) => {
		if (signal?.aborted) {
			reject(abortError());
			return;
		}
		const onAbort = () => {
			clearTimeout(timer);
			reject(abortError());
		};
		const timer = setTimeout(() => {
			// Each retry adds a listener; without this a long rebuild would pile them up.
			signal?.removeEventListener('abort', onAbort);
			resolve();
		}, ms);
		signal?.addEventListener('abort', onAbort, { once: true });
	});
}

/** Fetch JSON; while the index rebuilds, retry with backoff up to maxWaitMs. */
export async function fetchWhenIndexed<T>(
	url: string,
	options: FetchWhenIndexedOptions = {}
): Promise<T> {
	const { onRebuilding, signal, fetchFn = fetch, maxWaitMs = MAX_WAIT_MS } = options;
	let rebuilding = false;
	let waited = 0;
	const stopWaiting = () => {
		if (rebuilding) onRebuilding?.(false);
		rebuilding = false;
	};

	for (let attempt = 0; ; attempt++) {
		const res = await fetchFn(url, { signal });
		if (res.ok) {
			stopWaiting();
			return (await res.json()) as T;
		}

		const detail = await readDetail(res);
		// Reading the body can outlive an abort; report it as the abort it was.
		if (signal?.aborted) throw abortError();
		if (!(res.status === 503 && detail !== null && /index is rebuilding/i.test(detail))) {
			stopWaiting();
			// Any other answer is final, e.g. the index being switched off; show what the API said.
			throw new Error(detail ?? `API ${res.status}`);
		}

		const delay = retryDelayMs(res, attempt);
		if (waited + delay > maxWaitMs) {
			stopWaiting();
			throw new IndexStillRebuildingError();
		}
		if (!rebuilding) {
			rebuilding = true;
			onRebuilding?.(true);
		}
		await wait(delay, signal);
		waited += delay;
	}
}

/** True when a load stopped because its tab went away, which is not an error to show. */
export function isAbort(error: unknown): boolean {
	return error instanceof DOMException && error.name === 'AbortError';
}
