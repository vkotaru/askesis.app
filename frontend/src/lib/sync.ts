/**
 * Sync engine for askesis.app
 *
 * Handles the offline mutation queue (pendingSync) and server synchronization.
 * The FastAPI backend sync endpoints (GET /api/sync/changes, POST /api/sync/push)
 * don't exist yet — this module gracefully handles their absence.
 */

import { writable, derived, get } from 'svelte/store';
import { db, type PendingSyncEntry, type SyncOperation } from './db';
import { browser } from '$app/environment';

// ── Stores ───────────────────────────────────────────────────────────────────

export const isOnline = writable(browser ? navigator.onLine : true);
export const pendingSyncCount = writable(0);
export const isSyncing = writable(false);
export const lastSyncTime = writable<string | null>(null);

export const syncStatus = derived(
  [isOnline, pendingSyncCount, isSyncing],
  ([$online, $pending, $syncing]) => ({
    online: $online,
    pending: $pending,
    syncing: $syncing,
  })
);

// ── Online/offline detection ─────────────────────────────────────────────────

if (browser) {
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
    // Try the batch sync endpoint first (future)
    const pushed = await pushToServer(entries);
    if (pushed) {
      // Clear all successfully synced entries
      await db.pendingSync.clear();
      await refreshPendingSyncCount();
      lastSyncTime.set(new Date().toISOString());
    }
  } catch {
    // Server sync endpoints don't exist yet — that's OK.
    // Entries stay in the queue for next attempt.
  } finally {
    isSyncing.set(false);
  }
}

// ── Server communication (graceful fallback) ─────────────────────────────────

async function pushToServer(entries: PendingSyncEntry[]): Promise<boolean> {
  try {
    const res = await fetch('/api/sync/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ changes: entries }),
    });

    if (res.status === 404) {
      // Sync endpoint doesn't exist yet — not an error
      return false;
    }

    if (!res.ok) {
      throw new Error(`Sync push failed: HTTP ${res.status}`);
    }

    return true;
  } catch (err) {
    if (err instanceof TypeError) {
      // Network error — we're offline
      return false;
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
      // Sync endpoint doesn't exist yet — not an error
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

    lastSyncTime.set(new Date().toISOString());
  } catch {
    // Network error or sync endpoint doesn't exist — silently skip
  }
}

async function mergeServerRecord(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table: any,
  serverRecord: { id: number; deleted_at?: string; [key: string]: unknown }
): Promise<void> {
  const existing = await table.where('serverId').equals(serverRecord.id).first();

  if (serverRecord.deleted_at) {
    // Server says this record was deleted
    if (existing) {
      await table.delete(existing.localId);
    }
    return;
  }

  if (existing) {
    // Update existing local record with server data
    await table.update(existing.localId, {
      ...serverRecord,
      serverId: serverRecord.id,
      updatedAt: serverRecord.updated_at || new Date().toISOString(),
    });
  } else {
    // Insert new record from server
    await table.add({
      ...serverRecord,
      serverId: serverRecord.id,
      updatedAt: serverRecord.updated_at || new Date().toISOString(),
    });
  }
}

// ── Full sync cycle ──────────────────────────────────────────────────────────

export async function sync(): Promise<void> {
  await pullFromServer();
  await flushPendingSync();
}
