/**
 * Sync engine for askesis.app
 *
 * Handles the offline mutation queue (pendingSync) and server synchronization.
 */

import { writable, derived, get } from 'svelte/store';
import { type Table } from 'dexie';
import { db, type PendingSyncEntry, type SyncOperation } from './db';
import { currentUserId } from './stores/user';
import { browser } from '$app/environment';
import { apiUrl } from './config';

// ── Stores ───────────────────────────────────────────────────────────────────

export const isOnline = writable(browser ? navigator.onLine : true);
export const pendingSyncCount = writable(0);
export const isSyncing = writable(false);
export const lastSyncTime = writable<string | null>(null);
export const syncErrors = writable<string[]>([]);

/**
 * Every Dexie table a pendingSync entry's `table` field can name, so a queue
 * entry can be resolved back to the table it belongs to. Keep in step with
 * TABLE_MAP in backend/app/routers/sync.py.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SYNCED_TABLES: Record<string, Table<any, number>> = {
  dailyLogs: db.dailyLogs,
  dailyNutrition: db.dailyNutrition,
  activities: db.activities,
  meals: db.meals,
  foods: db.foods,
  measurements: db.measurements,
  photos: db.photos,
};

export const syncStatus = derived(
  [isOnline, pendingSyncCount, isSyncing],
  ([$online, $pending, $syncing]) => ({
    online: $online,
    pending: $pending,
    syncing: $syncing,
  })
);

// ── Persist lastSyncTime in Dexie ────────────────────────────────────────────

async function loadLastSyncTime() {
  try {
    const entry = await db.settings.get('lastSyncTime');
    if (entry?.value) {
      lastSyncTime.set(entry.value as string);
    }
  } catch {
    // DB might not be open yet
  }
}

async function saveLastSyncTime(time: string) {
  lastSyncTime.set(time);
  try {
    await db.settings.put({ key: 'lastSyncTime', value: time });
  } catch {
    // Best effort
  }
}

// ── Online/offline detection ─────────────────────────────────────────────────

if (browser) {
  loadLastSyncTime();

  window.addEventListener('online', () => {
    isOnline.set(true);
    flushPendingSync();
  });
  window.addEventListener('offline', () => {
    isOnline.set(false);
  });
}

// ── Queue ownership ──────────────────────────────────────────────────────────

/**
 * True if `entry` may be pushed under the session of `userId`.
 *
 * An untagged entry (queued before per-user tagging, and left untagged by the
 * v5 upgrade because the browser had seen more than one account) is still
 * pushed: the local DB is its only copy, and refusing to push it would strand
 * the user's work forever. That is the one case where ownership is a guess,
 * and it is bounded — nothing writes untagged entries any more.
 */
export function isQueueEntryOwnedBy(entry: PendingSyncEntry, userId?: number): boolean {
  return entry.userId == null || entry.userId === userId;
}

// ── Pending sync count ───────────────────────────────────────────────────────

/** Counts only what the current account can actually push, so another
 *  account's parked queue never shows up as this account's backlog. */
async function refreshPendingSyncCount() {
  try {
    const uid = currentUserId();
    const entries = await db.pendingSync.toArray();
    pendingSyncCount.set(entries.filter((e) => isQueueEntryOwnedBy(e, uid)).length);
  } catch {
    // DB might not be open yet
  }
}

// Refresh count on startup
if (browser) {
  refreshPendingSyncCount();
}

// ── Queue a mutation for sync ────────────────────────────────────────────────

export async function queueSync(
  table: string,
  operation: SyncOperation,
  localId: number,
  serverId?: number,
  data?: Record<string, unknown>
): Promise<void> {
  await db.pendingSync.add({
    table,
    operation,
    localId,
    serverId,
    data,
    timestamp: new Date().toISOString(),
    userId: currentUserId(),
  });
  await refreshPendingSyncCount();
}

// ── Queue collapsing ─────────────────────────────────────────────────────────

export interface CollapsedQueue {
  /** Entries that still have to go to the server, in push order. */
  toPush: PendingSyncEntry[];
  /** pendingSync ids that can simply be dropped without pushing anything. */
  dropIds: number[];
}

/**
 * Collapse create→…→delete chains that never reached the server.
 *
 * A row created offline and deleted again while still offline queues
 * `create(localId=L, serverId=undefined)` and later
 * `delete(localId=L, serverId=undefined)`. Pushed as-is, the create inserts a
 * server row and the delete — which carries no server id — has nothing to aim
 * at, so the row survives and the next revalidation pulls the user's deleted
 * entry straight back into the local DB.
 *
 * `push_changes` on the server resolves a same-batch pair from the create's
 * assigned id, and `applyServerIds` below backfills the id onto a still-queued
 * delete when the two land in different batches. This is the third guard and
 * the cheapest: if the whole life of a row is in the queue, don't push it at
 * all.
 *
 * Only fully-unsynced groups qualify. A single entry carrying a serverId means
 * the row exists on the server, so the delete has real work to do and the
 * group is pushed untouched.
 *
 * Entries must be in push (timestamp) order.
 */
export function collapseQueue(entries: PendingSyncEntry[]): CollapsedQueue {
  const groups = new Map<string, PendingSyncEntry[]>();
  for (const entry of entries) {
    const key = `${entry.table}:${entry.localId}`;
    const group = groups.get(key);
    if (group) group.push(entry);
    else groups.set(key, [entry]);
  }

  const dead = new Set<string>();
  for (const [key, group] of groups) {
    if (group[group.length - 1].operation !== 'delete') continue;
    if (group.some((e) => e.serverId != null)) continue;
    if (!group.some((e) => e.operation === 'create')) continue;
    dead.add(key);
  }

  if (dead.size === 0) return { toPush: entries, dropIds: [] };

  const toPush: PendingSyncEntry[] = [];
  const dropIds: number[] = [];
  for (const entry of entries) {
    if (dead.has(`${entry.table}:${entry.localId}`)) {
      if (entry.id != null) dropIds.push(entry.id);
    } else {
      toPush.push(entry);
    }
  }

  return { toPush, dropIds };
}

// ── Flush pending sync queue ─────────────────────────────────────────────────

export async function flushPendingSync(): Promise<void> {
  if (!get(isOnline)) return;
  if (get(isSyncing)) return;

  // Only this account's mutations. A queue parked by whoever signed out last
  // stays put until they sign back in; pushing it here would file their data
  // into the current account, because the server takes the owner from the
  // session and not from the payload.
  const uid = currentUserId();
  const queued = (await db.pendingSync.orderBy('timestamp').toArray()).filter((e) =>
    isQueueEntryOwnedBy(e, uid)
  );
  if (queued.length === 0) return;

  isSyncing.set(true);

  try {
    // Ties on `timestamp` (two writes in the same millisecond) fall back to
    // insertion order, which is the order the user actually made them in.
    queued.sort((a, b) => a.timestamp.localeCompare(b.timestamp) || (a.id ?? 0) - (b.id ?? 0));

    const { toPush, dropIds } = collapseQueue(queued);
    if (dropIds.length > 0) {
      await db.pendingSync.bulkDelete(dropIds);
      await refreshPendingSyncCount();
    }
    if (toPush.length === 0) return;

    const result = await pushToServer(toPush);
    if (result.pushed) {
      // Adopt server-assigned ids before dropping the queue entries. If this
      // throws, the entries are still queued and the push is retried — the
      // alternative is a row stranded with serverId == null and nothing left
      // to tell it what its id is.
      await applyServerIds(result.resolutions);

      // Only delete entries that the server confirmed as ok
      if (result.successIds.length > 0) {
        await db.pendingSync.bulkDelete(result.successIds);
      }
      await refreshPendingSyncCount();
      await saveLastSyncTime(new Date().toISOString());

      // Report any partial failures
      if (result.errors.length > 0) {
        syncErrors.set(result.errors);
        // Auto-clear errors after 10 seconds
        setTimeout(() => syncErrors.set([]), 10000);
      }
    }
  } catch (err) {
    // Entries stay in the queue for next attempt.
    // Surface non-network errors so the user knows what went wrong.
    const msg = err instanceof Error ? err.message : String(err);
    syncErrors.set([msg]);
    setTimeout(() => syncErrors.set([]), 10000);
  } finally {
    isSyncing.set(false);
  }
}

// ── Server communication ─────────────────────────────────────────────────────

/** One row's server id, as reported by a successful push. */
export interface ServerIdResolution {
  table: string;
  localId: number;
  serverId: number;
}

interface PushResult {
  pushed: boolean;
  successIds: number[];
  resolutions: ServerIdResolution[];
  errors: string[];
}

/** Shape of one entry in the /api/sync/push response. */
interface ServerPushResult {
  index: number;
  ok: boolean;
  serverId?: number | null;
  error?: string | null;
}

/**
 * Pair up the server's per-change results with the entries that produced them.
 *
 * Split out from the fetch so it can be reasoned about (and tested) without a
 * network or a Dexie.
 */
export function readPushResponse(
  entries: PendingSyncEntry[],
  results: ServerPushResult[]
): { successIds: number[]; resolutions: ServerIdResolution[]; errors: string[] } {
  const successIds: number[] = [];
  const resolutions: ServerIdResolution[] = [];
  const errors: string[] = [];

  for (const r of results) {
    const entry = entries[r.index];
    if (!entry) continue;

    if (r.ok) {
      if (entry.id != null) successIds.push(entry.id);
      // The server returns the row's real id for creates and updates (an
      // update for a row it has never seen falls through to a create there, so
      // that can mint an id too). Deletes return none. Throwing this away is
      // what left offline-created rows with serverId == null forever.
      if (r.serverId != null && entry.operation !== 'delete') {
        resolutions.push({ table: entry.table, localId: entry.localId, serverId: r.serverId });
      }
    } else if (r.error) {
      errors.push(`Sync error (${entry.table || '?'}): ${r.error}`);
    }
  }

  return { successIds, resolutions, errors };
}

/**
 * Write server-assigned ids back onto the local rows they belong to.
 *
 * Without this a row created offline never learns its server id: the next
 * revalidation can't match it, inserts a second copy alongside it, and every
 * later edit of that ghost sends its *local* id to the server as if it were a
 * server id — overwriting an unrelated record.
 *
 * Concurrency:
 * - Only the `serverId` field is written, so an edit the user made while the
 *   push was in flight is untouched.
 * - A row deleted meanwhile is not re-added; resurrecting it would undo the
 *   delete. Its queue entries are still backfilled, so the queued delete can
 *   find the right server row.
 * - A row that already carries a serverId is left alone: something already
 *   reconciled it (a direct online write, or a merge), and that id is the one
 *   the rest of the DB has been referring to.
 */
async function applyServerIds(resolutions: ServerIdResolution[]): Promise<void> {
  if (resolutions.length === 0) return;

  // Queue entries for the same row that still have no server id — typically a
  // delete or update queued while the create was in flight, which would
  // otherwise be a no-op on the server and lose the mutation.
  const uid = currentUserId();
  const unresolvedByRow = new Map<string, PendingSyncEntry[]>();
  for (const entry of await db.pendingSync.toArray()) {
    if (entry.id == null || entry.serverId != null) continue;
    if (!isQueueEntryOwnedBy(entry, uid)) continue;
    const key = `${entry.table}:${entry.localId}`;
    const list = unresolvedByRow.get(key);
    if (list) list.push(entry);
    else unresolvedByRow.set(key, [entry]);
  }

  for (const { table, localId, serverId } of resolutions) {
    try {
      const target = SYNCED_TABLES[table];
      if (target) {
        const row = await target.get(localId);
        if (row && row.serverId == null) {
          await target.update(localId, { serverId });
        }
      }

      for (const entry of unresolvedByRow.get(`${table}:${localId}`) ?? []) {
        await db.pendingSync.update(entry.id!, { serverId });
      }
    } catch (err) {
      // One row failing to adopt its id must not abort the others.
      console.warn(`[askesis] Failed to adopt serverId for ${table}#${localId}:`, err);
    }
  }
}

async function pushToServer(entries: PendingSyncEntry[]): Promise<PushResult> {
  try {
    const res = await fetch(apiUrl('/api/sync/push'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ changes: entries }),
    });

    if (res.status === 404) {
      return { pushed: false, successIds: [], resolutions: [], errors: [] };
    }

    if (!res.ok) {
      throw new Error(`Sync push failed: HTTP ${res.status}`);
    }

    const data: { results?: ServerPushResult[] } = await res.json();
    const { successIds, resolutions, errors } = readPushResponse(entries, data.results ?? []);

    return { pushed: true, successIds, resolutions, errors };
  } catch (err) {
    if (err instanceof TypeError) {
      // Network error — we're offline
      return { pushed: false, successIds: [], resolutions: [], errors: [] };
    }
    throw err;
  }
}

export async function pullFromServer(): Promise<void> {
  if (!get(isOnline)) return;
  // Signed out there is no account to file the rows under, and an untagged row
  // is unreadable anyway. /api/sync/changes would 401 regardless.
  const ownerId = currentUserId();
  if (ownerId == null) return;

  try {
    const lastSync = get(lastSyncTime) || '1970-01-01T00:00:00Z';
    const res = await fetch(
      apiUrl(`/api/sync/changes?since=${encodeURIComponent(lastSync)}`),
      { credentials: 'include' },
    );

    if (res.status === 404) {
      return;
    }

    if (!res.ok) return;

    const data = await res.json();

    // Merge server changes into Dexie
    if (data.dailyLogs) {
      for (const log of data.dailyLogs) {
        await mergeServerRecord(db.dailyLogs, log, ownerId, true);
      }
    }
    if (data.dailyNutrition) {
      for (const nutrition of data.dailyNutrition) {
        await mergeServerRecord(db.dailyNutrition, nutrition, ownerId, true);
      }
    }
    if (data.activities) {
      for (const activity of data.activities) {
        await mergeServerRecord(db.activities, activity, ownerId);
      }
    }
    if (data.meals) {
      for (const meal of data.meals) {
        await mergeServerRecord(db.meals, meal, ownerId);
      }
    }
    if (data.foods) {
      for (const food of data.foods) {
        // The food catalogue is shared and carries no owner.
        await mergeServerRecord(db.foods, food, undefined);
      }
    }
    if (data.measurements) {
      for (const measurement of data.measurements) {
        await mergeServerRecord(db.measurements, measurement, ownerId, true);
      }
    }
    if (data.photos) {
      for (const photo of data.photos) {
        await mergeServerRecord(db.photos, photo, ownerId);
      }
    }

    await saveLastSyncTime(new Date().toISOString());
  } catch {
    // Network error — silently skip
  }
}

async function mergeServerRecord(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table: Table<any, number>,
  serverRecord: { id: number; deleted_at?: string; date?: string; [key: string]: unknown },
  /** Account the pulled rows belong to. Stamped onto every row written here:
   *  an untagged row is invisible to the read layer, which filters by owner. */
  ownerId: number | undefined,
  // Only true for tables the app treats as one row per date: daily logs,
  // measurements and daily nutrition, all of which the UI edits as "the row
  // for this day". That is an application invariant, not a schema one — of the
  // three, only `daily_nutrition` actually has a UniqueConstraint on
  // (user_id, date); `daily_logs` and `body_measurements` carry a plain
  // non-unique Index, and the server upserts them by date in `_handle_create`
  // to hold the invariant up. Activities, meals and photos legitimately hold
  // several rows per date, so matching on date there picks an arbitrary
  // unrelated row.
  dateIsUnique = false
): Promise<void> {
  let existing = await table.where('serverId').equals(serverRecord.id).first();
  const matchedByServerId = existing !== undefined;

  // Fall back to date only to adopt a local create the server hasn't assigned
  // an id to yet — that is the case this fallback was written for. Restricting
  // it to serverId == null is what keeps it from overwriting an already-synced
  // row that merely shares a date, and to the owner is what keeps one account's
  // pull from swallowing the other account's unsynced row for the same day.
  if (!existing && dateIsUnique && serverRecord.date) {
    existing = await table
      .where('date')
      .equals(serverRecord.date)
      .filter((r) => r.serverId == null && r.userId === ownerId)
      .first();
  }

  if (serverRecord.deleted_at) {
    // Delete only what we matched by serverId. A date match is a guess, and
    // this is a hard delete — getting it wrong destroys a row whose only copy
    // may be local.
    if (existing && matchedByServerId) {
      await table.delete(existing.localId);
    }
    return;
  }

  const merged = {
    ...serverRecord,
    serverId: serverRecord.id,
    // The server row's own user_id wins; `ownerId` covers models that don't
    // carry one. Rows written without an owner are unreadable by design.
    userId: typeof serverRecord.user_id === 'number' ? serverRecord.user_id : ownerId,
    updatedAt: serverRecord.updated_at || new Date().toISOString(),
  };

  if (existing) {
    await table.update(existing.localId, merged);
  } else {
    await table.add(merged);
  }
}

// ── Full sync cycle ──────────────────────────────────────────────────────────

export async function sync(): Promise<void> {
  await pullFromServer();
  await flushPendingSync();
}

// ── Local profile → cloud account migration ──────────────────────────────────
//
// Local-profile mode (an account-less identity kept in localStorage) is gone,
// but a browser that used it still holds those rows in IndexedDB, and they
// exist nowhere else. These two helpers find that data and hand it to the
// signed-in account; MigrateLocalDataBanner.svelte drives them after login.

interface MigrationCounts {
  dailyLogs: number;
  activities: number;
  meals: number;
  foods: number;
  measurements: number;
  photosSkipped: number;
}

/**
 * localId sets, per table, of rows that already have a queued mutation.
 *
 * These are NOT stranded: local-profile mode left its writes in pendingSync
 * (every write falls back to the queue when the API call 401s, which is what
 * every write did with no session), and now that nothing short-circuits
 * flushPendingSync they go up on the first sync after login, under the
 * signed-in account. Re-queueing them as well would push the same row twice,
 * and `_handle_create` on the server only upserts DailyLog and DailyNutrition
 * — activities, meals, measurements and foods would insert a second copy.
 */
async function queuedLocalIdsByTable(): Promise<Map<string, Set<number>>> {
  const byTable = new Map<string, Set<number>>();
  for (const entry of await db.pendingSync.toArray()) {
    let ids = byTable.get(entry.table);
    if (!ids) {
      ids = new Set<number>();
      byTable.set(entry.table, ids);
    }
    ids.add(entry.localId);
  }
  return byTable;
}

/**
 * Count Dexie rows that belong to an old local profile and have no route to
 * the server: no serverId (never synced) and no pendingSync entry (not on
 * their way either). For every table but `foods` that also means a userId
 * that isn't the current account's; local foods carry no userId at all.
 *
 * Photos are counted but never migrated — the bytes have to round-trip
 * through /api/photos/upload, which is not a sync-queue operation.
 */
export async function countLocalProfileData(currentUserId: number): Promise<MigrationCounts> {
  const queued = await queuedLocalIdsByTable();

  const isStranded =
    (tableName: string, requireForeignUser = true) =>
    (row: { localId?: number; userId?: number; serverId?: number }) => {
      if (row.serverId != null) return false;
      if (row.localId != null && queued.get(tableName)?.has(row.localId)) return false;
      if (!requireForeignUser) return true;
      return row.userId != null && row.userId !== currentUserId;
    };

  const [dailyLogs, activities, meals, foods, measurements, photos] = await Promise.all([
    db.dailyLogs.filter(isStranded('dailyLogs')).count(),
    db.activities.filter(isStranded('activities')).count(),
    db.meals.filter(isStranded('meals')).count(),
    db.foods.filter(isStranded('foods', false)).count(),
    db.measurements.filter(isStranded('measurements')).count(),
    db.photos.filter(isStranded('photos')).count(),
  ]);

  return {
    dailyLogs,
    activities,
    meals,
    foods,
    measurements,
    photosSkipped: photos,
  };
}

/**
 * Reassign every stranded local-profile row to currentUserId and queue it as
 * a create. Selection matches countLocalProfileData exactly, so the banner
 * never promises to move more than this moves.
 *
 * Returns the totals migrated.
 */
export async function migrateLocalToCloud(currentUserId: number): Promise<MigrationCounts> {
  const counts: MigrationCounts = {
    dailyLogs: 0,
    activities: 0,
    meals: 0,
    foods: 0,
    measurements: 0,
    photosSkipped: 0,
  };

  type MigratableTable = 'dailyLogs' | 'activities' | 'meals' | 'foods' | 'measurements';

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tables: Array<{ name: MigratableTable; table: Table<any, number> }> = [
    { name: 'dailyLogs', table: db.dailyLogs },
    { name: 'activities', table: db.activities },
    { name: 'meals', table: db.meals },
    { name: 'foods', table: db.foods },
    { name: 'measurements', table: db.measurements },
  ];

  const queued = await queuedLocalIdsByTable();

  for (const { name, table } of tables) {
    const rows = await table.toArray();
    for (const row of rows) {
      if (row.serverId != null) continue;
      // Already queued: the sync engine will push it. Queueing a second
      // create would insert a duplicate on the server for every table except
      // dailyLogs, which is the only one _handle_create upserts by date.
      if (row.localId != null && queued.get(name)?.has(row.localId)) continue;
      // Foods don't have userId in the local schema, but they still need a
      // server-side create if they weren't synced. Everything else gets the
      // old-userId check.
      if (name !== 'foods' && (row.userId == null || row.userId === currentUserId)) continue;

      row.userId = currentUserId;
      row.updatedAt = new Date().toISOString();
      await table.put(row);

      // Re-queue as create. The sync engine will assign serverIds on push.
      await queueSync(name, 'create', row.localId!, undefined, row as Record<string, unknown>);
      counts[name] += 1;
    }
  }

  // Photos: count but don't queue. Photo bytes have to round-trip through
  // /api/photos/upload, which isn't a sync-queue operation. Follow-up.
  counts.photosSkipped = await db.photos
    .filter(
      (r) =>
        r.serverId == null &&
        !(r.localId != null && queued.get('photos')?.has(r.localId)) &&
        r.userId != null &&
        r.userId !== currentUserId
    )
    .count();

  // Kick the push immediately so the user sees progress.
  flushPendingSync().catch(() => {});

  return counts;
}
