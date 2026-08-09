/**
 * Sync engine for askesis.app
 *
 * Handles the offline mutation queue (pendingSync) and server synchronization.
 */

import { writable, derived, get } from 'svelte/store';
import { type Table } from 'dexie';
import { db, type PendingSyncEntry, type SyncOperation } from './db';
import { browser } from '$app/environment';
import { apiUrl } from './config';

// ── Stores ───────────────────────────────────────────────────────────────────

export const isOnline = writable(browser ? navigator.onLine : true);
export const pendingSyncCount = writable(0);
export const isSyncing = writable(false);
export const lastSyncTime = writable<string | null>(null);
export const syncErrors = writable<string[]>([]);

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

// ── Pending sync count ───────────────────────────────────────────────────────

async function refreshPendingSyncCount() {
  try {
    const count = await db.pendingSync.count();
    pendingSyncCount.set(count);
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
  });
  await refreshPendingSyncCount();
}

// ── Flush pending sync queue ─────────────────────────────────────────────────

export async function flushPendingSync(): Promise<void> {
  if (!get(isOnline)) return;
  if (get(isSyncing)) return;

  const entries = await db.pendingSync.orderBy('timestamp').toArray();
  if (entries.length === 0) return;

  isSyncing.set(true);

  try {
    const result = await pushToServer(entries);
    if (result.pushed) {
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

interface PushResult {
  pushed: boolean;
  successIds: number[];
  errors: string[];
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
      return { pushed: false, successIds: [], errors: [] };
    }

    if (!res.ok) {
      throw new Error(`Sync push failed: HTTP ${res.status}`);
    }

    const data = await res.json();
    const successIds: number[] = [];
    const errors: string[] = [];

    if (data.results) {
      for (const r of data.results) {
        if (r.ok) {
          const entryId = entries[r.index]?.id;
          if (entryId != null) successIds.push(entryId);
        } else if (r.error) {
          errors.push(`Sync error (${entries[r.index]?.table || '?'}): ${r.error}`);
        }
      }
    }

    return { pushed: true, successIds, errors };
  } catch (err) {
    if (err instanceof TypeError) {
      // Network error — we're offline
      return { pushed: false, successIds: [], errors: [] };
    }
    throw err;
  }
}

export async function pullFromServer(): Promise<void> {
  if (!get(isOnline)) return;

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
        await mergeServerRecord(db.dailyLogs, log, true);
      }
    }
    if (data.dailyNutrition) {
      for (const nutrition of data.dailyNutrition) {
        await mergeServerRecord(db.dailyNutrition, nutrition, true);
      }
    }
    if (data.activities) {
      for (const activity of data.activities) {
        await mergeServerRecord(db.activities, activity);
      }
    }
    if (data.meals) {
      for (const meal of data.meals) {
        await mergeServerRecord(db.meals, meal);
      }
    }
    if (data.foods) {
      for (const food of data.foods) {
        await mergeServerRecord(db.foods, food);
      }
    }
    if (data.measurements) {
      for (const measurement of data.measurements) {
        await mergeServerRecord(db.measurements, measurement, true);
      }
    }
    if (data.photos) {
      for (const photo of data.photos) {
        await mergeServerRecord(db.photos, photo);
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
  // Only true for tables the server keeps at one row per date (daily logs,
  // measurements, daily nutrition — all of which have a unique (user_id, date)
  // constraint). Activities, meals and photos legitimately hold several rows
  // per date, so matching on date there picks an arbitrary unrelated row.
  dateIsUnique = false
): Promise<void> {
  let existing = await table.where('serverId').equals(serverRecord.id).first();
  const matchedByServerId = existing !== undefined;

  // Fall back to date only to adopt a local create the server hasn't assigned
  // an id to yet — that is the case this fallback was written for. Restricting
  // it to serverId == null is what keeps it from overwriting an already-synced
  // row that merely shares a date.
  if (!existing && dateIsUnique && serverRecord.date) {
    existing = await table
      .where('date')
      .equals(serverRecord.date)
      .filter((r) => r.serverId == null)
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
