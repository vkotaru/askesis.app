/**
 * Sync engine for askesis.app
 *
 * Handles the offline mutation queue (pendingSync) and server synchronization.
 */

import { writable, derived, get } from 'svelte/store';
import { db, type PendingSyncEntry, type SyncOperation } from './db';
import { browser } from '$app/environment';

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
      // Clear successfully synced entries
      await db.pendingSync.clear();
      await refreshPendingSyncCount();
      await saveLastSyncTime(new Date().toISOString());

      // Report any partial failures
      if (result.errors.length > 0) {
        syncErrors.set(result.errors);
        // Auto-clear errors after 10 seconds
        setTimeout(() => syncErrors.set([]), 10000);
      }
    }
  } catch {
    // Entries stay in the queue for next attempt.
  } finally {
    isSyncing.set(false);
  }
}

// ── Server communication ─────────────────────────────────────────────────────

interface PushResult {
  pushed: boolean;
  errors: string[];
}

async function pushToServer(entries: PendingSyncEntry[]): Promise<PushResult> {
  try {
    const res = await fetch('/api/sync/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ changes: entries }),
    });

    if (res.status === 404) {
      return { pushed: false, errors: [] };
    }

    if (!res.ok) {
      throw new Error(`Sync push failed: HTTP ${res.status}`);
    }

    const data = await res.json();
    const errors: string[] = [];

    if (data.results) {
      for (const r of data.results) {
        if (!r.ok && r.error) {
          errors.push(`Sync error (${entries[r.index]?.table || '?'}): ${r.error}`);
        }
      }
    }

    return { pushed: true, errors };
  } catch (err) {
    if (err instanceof TypeError) {
      // Network error — we're offline
      return { pushed: false, errors: [] };
    }
    throw err;
  }
}

export async function pullFromServer(): Promise<void> {
  if (!get(isOnline)) return;

  try {
    const lastSync = get(lastSyncTime) || '1970-01-01T00:00:00Z';
    const res = await fetch(`/api/sync/changes?since=${encodeURIComponent(lastSync)}`, {
      credentials: 'include',
    });

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

    await saveLastSyncTime(new Date().toISOString());
  } catch {
    // Network error — silently skip
  }
}

async function mergeServerRecord(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table: any,
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
  await pullFromServer();
  await flushPendingSync();
}
