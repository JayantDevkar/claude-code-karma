/** Client-side loader for the heavy session tabs (timeline, file activity, subagents). */

export type TabResourceKind = 'timeline' | 'file-activity' | 'subagents';

export interface TabResourceResult<T> {
	uuid: string;
	kind: TabResourceKind;
	data: T;
}

type FetchFn = (url: string) => Promise<Response>;

export const TAB_CACHE_SESSIONS = 3;

// Map insertion order doubles as recency: the first key is the least recently used session
const cache = new Map<string, Map<TabResourceKind, unknown>>();
const inflight = new Map<string, Promise<TabResourceResult<unknown>>>();

function inflightKey(uuid: string, kind: TabResourceKind): string {
	return `${uuid}\u0000${kind}`;
}

function touch(uuid: string): Map<TabResourceKind, unknown> | undefined {
	const entry = cache.get(uuid);
	if (entry) {
		cache.delete(uuid);
		cache.set(uuid, entry);
	}
	return entry;
}

function store(uuid: string, kind: TabResourceKind, data: unknown): void {
	const entry = touch(uuid) ?? new Map<TabResourceKind, unknown>();
	entry.set(kind, data);
	cache.set(uuid, entry);
	while (cache.size > TAB_CACHE_SESSIONS) {
		const oldest = cache.keys().next().value as string;
		cache.delete(oldest);
	}
}

/** Cached data for (uuid, kind), or undefined when it has to be fetched. */
export function peekTabResource<T>(uuid: string, kind: TabResourceKind): T | undefined {
	const entry = touch(uuid);
	return entry?.has(kind) ? (entry.get(kind) as T) : undefined;
}

/** Fetch once per (uuid, kind); concurrent callers share the request and later ones hit the cache. */
export function loadTabResource<T>(
	uuid: string,
	kind: TabResourceKind,
	url: string,
	fetchFn: FetchFn = (u) => fetch(u)
): Promise<TabResourceResult<T>> {
	const entry = touch(uuid);
	if (entry?.has(kind)) {
		return Promise.resolve({ uuid, kind, data: entry.get(kind) as T });
	}

	const key = inflightKey(uuid, kind);
	const pending = inflight.get(key);
	if (pending) return pending as Promise<TabResourceResult<T>>;

	// Compared by identity below so an invalidate() during the request is detectable
	let request!: Promise<TabResourceResult<T>>;
	request = (async () => {
		try {
			const res = await fetchFn(url);
			if (!res.ok) throw new Error(`${kind} request failed: HTTP ${res.status}`);
			const data = (await res.json()) as T;
			// An invalidate() during the request means this result may already be stale
			if (inflight.get(key) === request) store(uuid, kind, data);
			return { uuid, kind, data };
		} finally {
			if (inflight.get(key) === request) inflight.delete(key);
		}
	})();
	inflight.set(key, request);
	return request;
}

/** Drop cached data (one kind, or every kind) so the next load refetches. */
export function invalidateTabResource(uuid: string, kind?: TabResourceKind): void {
	const kinds: TabResourceKind[] = kind ? [kind] : ['timeline', 'file-activity', 'subagents'];
	const entry = cache.get(uuid);
	for (const k of kinds) {
		entry?.delete(k);
		inflight.delete(inflightKey(uuid, k));
	}
	if (entry && entry.size === 0) cache.delete(uuid);
}

/** Test helper: forget every cached session and in-flight request. */
export function clearTabResourceCache(): void {
	cache.clear();
	inflight.clear();
}

/** Uuids currently cached, least recently used first. */
export function cachedTabSessions(): string[] {
	return [...cache.keys()];
}
