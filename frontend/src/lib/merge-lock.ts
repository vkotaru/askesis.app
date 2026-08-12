/**
 * The one lock every server→Dexie merge runs under.
 *
 * Two independent code paths write server data into the local DB:
 *
 *  - `hydrateFromServer` → `mergeServerRows` (cold start, one bulk page per table)
 *  - `pullFromServer` → `mergeServerRecord` (the incremental /api/sync/changes feed)
 *
 * Both are "insert if we don't already have it" logic built out of separate
 * awaited reads and writes, so without a lock they interleave: one path reads
 * an empty table, yields at an `await`, the other inserts the whole dataset,
 * and then the first path's insert runs anyway. On a fresh browser that is the
 * entire server dataset, twice — every row rendered twice.
 *
 * Ordering the two calls at startup would not fix it. Both are reachable
 * independently afterwards (a revalidation on any list page, a `sync()` after
 * reconnecting), so the mutual exclusion has to live at the merge itself.
 *
 * This module deliberately holds nothing but the lock and imports nothing, so
 * `sync.ts` and `stores/data.ts` can both use it without an import cycle.
 */

/** Tail of the chain of merges. Merges await it; fetches stay parallel. */
let mergeChain: Promise<unknown> = Promise.resolve();

/**
 * Run `fn` once every previously scheduled merge has settled.
 *
 * Only the read-modify-write is serialized — callers should do their network
 * fetch *before* entering, so concurrent revalidations still overlap on the
 * wire. A rejection is contained: it propagates to that caller only and the
 * chain keeps running.
 */
export function serializeMerge<T>(fn: () => Promise<T>): Promise<T> {
  const next = mergeChain.then(fn, fn);
  mergeChain = next.catch(() => {});
  return next;
}
