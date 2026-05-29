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
import { authHeaders } from './auth';

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
  if (localStorage.getItem('askesis_local_user')) return;
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
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
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
  if (localStorage.getItem('askesis_local_user')) return;
  if (!get(isOnline)) return;

  try {
    const lastSync = get(lastSyncTime) || '1970-01-01T00:00:00Z';
    const res = await fetch(
      apiUrl(`/api/sync/changes?since=${encodeURIComponent(lastSync)}`),
      {
        headers: await authHeaders(),
        credentials: 'include',
      },
    );

    if (res.status === 404) {
      return;
    }

    if (!res.ok) return;

    const data = await res.json();

    // Merge server changes into Dexie
    if (data.dailyLogs) {
      for (const log of data.dailyLogs) {
        await mergeServerRecord(db.dailyLogs, log);
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
        await mergeServerRecord(db.measurements, measurement);
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
  serverRecord: { id: number; deleted_at?: string; date?: string; [key: string]: unknown }
): Promise<void> {
  // Look up by serverId first, then fall back to date (prevents duplicates
  // when a local record was created before the server assigned an ID)
  let existing = await table.where('serverId').equals(serverRecord.id).first();
  if (!existing && serverRecord.date) {
    existing = await table.where('date').equals(serverRecord.date).first();
  }

  if (serverRecord.deleted_at) {
    if (existing) {
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
  if (localStorage.getItem('askesis_local_user')) return;
  await pullFromServer();
  await flushPendingSync();
}

// ── Local profile → cloud account migration ──────────────────────────────────

interface MigrationCounts {
  dailyLogs: number;
  activities: number;
  meals: number;
  foods: number;
  measurements: number;
  photosSkipped: number;
}

/**
 * Detect Dexie rows owned by an old local profile and re-target them at the
 * current cloud user. Returns the per-table count of rows that will be
 * pushed on the next sync.
 *
 * "Local profile rows" = rows with a userId that doesn't match the current
 * cloud user AND no serverId (never synced). Photos are intentionally
 * counted but not migrated — they need a real file upload, not a sync-queue
 * entry, which we defer to a follow-up.
 */
export async function countLocalProfileData(currentUserId: number): Promise<MigrationCounts> {
  const matches = (row: { userId?: number; serverId?: number }) =>
    row.serverId == null && row.userId != null && row.userId !== currentUserId;

  const [dailyLogs, activities, meals, foods, measurements, photos] = await Promise.all([
    db.dailyLogs.filter(matches).count(),
    db.activities.filter(matches).count(),
    db.meals.filter(matches).count(),
    db.foods.filter((r) => r.serverId == null).count(),
    db.measurements.filter(matches).count(),
    db.photos.filter(matches).count(),
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
 * Reassign every local-profile row to currentUserId and queue it as a create.
 * The server-side push handler upserts on (user_id, date) so re-importing
 * the same data twice is safe.
 *
 * Returns the totals migrated.
 */
export async function migrateLocalToCloud(currentUserId: number): Promise<MigrationCounts> {
  if (localStorage.getItem('askesis_local_user')) {
    throw new Error('Sign in to a cloud account before migrating local data');
  }

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

  for (const { name, table } of tables) {
    const rows = await table.toArray();
    for (const row of rows) {
      // Foods don't have userId in the local schema, but they still need a
      // server-side create if they weren't synced. Everything else gets the
      // old-userId check.
      if (row.serverId != null) continue;
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
    .filter((r) => r.serverId == null && r.userId != null && r.userId !== currentUserId)
    .count();

  // Kick the push immediately so the user sees progress.
  flushPendingSync().catch(() => {});

  return counts;
}
