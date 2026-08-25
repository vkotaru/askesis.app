/**
 * Dexie.js client-side database for askesis.app
 *
 * SCHEMA VERSIONING RULES (for future agents):
 * - Versions are APPEND-ONLY. Never delete or modify old version blocks.
 * - Each schema change = new db.version(N) with an .upgrade() migration.
 * - When the service worker updates and the page reloads, Dexie auto-migrates
 *   on db.open() by running any pending .upgrade() functions in sequence.
 * - Test migration paths: v1→v2, v1→v3 (skip), v2→v3.
 * - Only indexed fields are listed in the schema. Non-indexed fields are stored
 *   automatically — Dexie is schemaless for non-indexed properties.
 *
 * INDEX SYNTAX:
 *   ++localId  = auto-increment primary key
 *   serverId   = indexed field
 *   [a+b]      = compound index
 *   &field     = unique index
 */

import Dexie, { type Table } from 'dexie';

// ── Local record types (mirrors server types + local sync fields) ────────────

export interface LocalDailyLog {
  localId?: number;
  serverId?: number;
  date: string;
  userId?: number;
  weight?: number;
  sleep_hours?: number;
  steps?: number;
  water_ml?: number;
  feelings?: string[];
  caffeine_mg?: number;
  ate_outside?: boolean;
  notes?: string;
  // Per-field provenance from the server, e.g. { steps: 'garmin' }. Not
  // indexed, so it needs no schema version bump — Dexie is schemaless for
  // anything it is not asked to index. Rows cached before this existed simply
  // lack it, and absent means unknown, which is the pre-existing behaviour.
  sources?: Record<string, string>;
  updatedAt: string;
}

export interface LocalActivity {
  localId?: number;
  serverId?: number;
  date: string;
  userId?: number;
  name: string;
  activity_type: 'cardio' | 'strength';
  time_of_day?: string;
  duration_mins?: number;
  calories?: number;
  distance_km?: number;
  url?: string;
  notes?: string;
  tags?: string;
  icon?: string;
  // Importer that created this row; absent for hand-entered ones. Not indexed.
  source?: string;
  external_id?: string;
  exercises: Array<{
    id?: number;
    name: string;
    sets?: number;
    reps?: string;
    weight_kg?: number;
    notes?: string;
  }>;
  updatedAt: string;
}

export interface LocalMeal {
  localId?: number;
  serverId?: number;
  date: string;
  userId?: number;
  label: string;
  time?: string;
  calories?: number;
  description?: string;
  photo_path?: string;
  ai_analysis?: string;
  photo_url?: string;
  food_items?: Array<{
    id?: number;
    food_item_id: number;
    food_item_name: string;
    serving_size: number;
    serving_unit: string;
    quantity: number;
    calories?: number;
    protein_g?: number;
    carbs_g?: number;
    fat_g?: number;
    notes?: string;
  }>;
  computed_calories?: number;
  computed_protein_g?: number;
  computed_carbs_g?: number;
  computed_fat_g?: number;
  updatedAt: string;
}

export interface LocalFood {
  localId?: number;
  serverId?: number;
  name: string;
  brand?: string;
  category?: string;
  serving_size: number;
  serving_unit: string;
  calories?: number;
  protein_g?: number;
  carbs_g?: number;
  fat_g?: number;
  fiber_g?: number;
  is_shared: boolean;
  source?: string;
  updatedAt: string;
}

export interface LocalMeasurement {
  localId?: number;
  serverId?: number;
  date: string;
  userId?: number;
  neck?: number;
  shoulders?: number;
  chest?: number;
  bicep_left?: number;
  bicep_right?: number;
  forearm_left?: number;
  forearm_right?: number;
  waist?: number;
  abdomen?: number;
  hips?: number;
  thigh_left?: number;
  thigh_right?: number;
  calf_left?: number;
  calf_right?: number;
  notes?: string;
  updatedAt: string;
}

export interface LocalPhoto {
  localId?: number;
  serverId?: number;
  date: string;
  userId?: number;
  view: 'front' | 'side' | 'back';
  notes?: string;
  url?: string;
  updatedAt: string;
}

export interface LocalDailyNutrition {
  localId?: number;
  serverId?: number;
  date: string;
  userId?: number;
  protein_g?: number;
  carbs_g?: number;
  fat_g?: number;
  notes?: string;
  updatedAt: string;
}

export interface LocalSetting {
  key: string;
  value: unknown;
}

export type SyncOperation = 'create' | 'update' | 'delete';

export interface PendingSyncEntry {
  id?: number;
  table: string;
  operation: SyncOperation;
  localId: number;
  serverId?: number;
  data?: Record<string, unknown>;
  timestamp: string;
  /**
   * The account that queued this mutation.
   *
   * A shared browser can hold a queue belonging to whoever was signed in last,
   * and pushing it under a different session would file one person's data into
   * the other's account (`_handle_create` on the server takes the *session's*
   * user, not the payload's). The flush therefore only pushes entries owned by
   * the current user. Undefined means "queued before per-user tagging existed"
   * — see `shouldAdoptUntaggedRows` for how those are resolved.
   */
  userId?: number;
}

// ── One-shot duplicate cleanup ───────────────────────────────────────────────

/**
 * Settings key that records that the one-time "one row per date" cleanup has
 * already run. Stranded duplicates come from old sync bugs; once cleaned they
 * don't come back, so this must never run on every mount.
 */
export const DEDUPE_BY_DATE_FLAG = 'dedupeByDateV1';

interface DatedRow {
  localId?: number;
  serverId?: number;
  date: string;
}

/** Anything the duplicate tie-break can be applied to. */
export interface DedupeCandidate {
  localId?: number;
  serverId?: number;
}

/**
 * THE duplicate tie-break rule. One rule, one place.
 *
 * When two local rows describe the same thing — same serverId, or same date in
 * a one-row-per-date table — this decides which one is canonical:
 *
 *  1. A row the server has seen (`serverId != null`) beats one it hasn't. It is
 *     the row every later merge will match by serverId, and the row whose edits
 *     can actually be pushed under an existing id.
 *  2. Otherwise the lowest `localId` wins: the oldest row is the one the rest of
 *     the DB (and any queued mutation) is most likely to reference, and the
 *     choice is stable across re-runs.
 *
 * Every caller must use this — list rendering, single-row lookups, saves and
 * the cleanup sweeps alike. When the list view and the detail view disagreed
 * about which duplicate is real, the detail view wrote to a row the list never
 * rendered and the edit looked like it did nothing.
 */
export function preferRow<T extends DedupeCandidate>(a: T, b: T): T {
  const aSynced = a.serverId != null;
  const bSynced = b.serverId != null;
  if (aSynced !== bSynced) return aSynced ? a : b;
  // A row without a localId can't be addressed at all, so it never wins a tie.
  const aLocal = a.localId ?? Number.MAX_SAFE_INTEGER;
  const bLocal = b.localId ?? Number.MAX_SAFE_INTEGER;
  return aLocal <= bLocal ? a : b;
}

/** The canonical row of a set of duplicates, per `preferRow`. */
export function pickCanonicalRow<T extends DedupeCandidate>(rows: T[]): T | undefined {
  let best: T | undefined;
  for (const row of rows) best = best === undefined ? row : preferRow(best, row);
  return best;
}

/**
 * For tables that hold at most one row per date (dailyLogs, measurements),
 * return the localIds of the rows that should be dropped. The survivor is the
 * one `preferRow` picks.
 */
export function findDuplicateDateIds(rows: DatedRow[]): number[] {
  const keep = new Map<string, DatedRow>();
  const toDelete: number[] = [];

  for (const row of rows) {
    const existing = keep.get(row.date);
    if (!existing) {
      keep.set(row.date, row);
      continue;
    }
    const winner = preferRow(existing, row);
    const loser = winner === existing ? row : existing;
    keep.set(row.date, winner);
    if (loser.localId != null) toDelete.push(loser.localId);
  }

  return toDelete;
}

/** Every table whose rows carry a serverId assigned by the sync engine. */
export const SYNCED_TABLES = [
  'dailyLogs',
  'activities',
  'meals',
  'foods',
  'measurements',
  'photos',
  'dailyNutrition',
] as const;

/**
 * The synced tables whose rows belong to exactly one account.
 *
 * `foods` is deliberately absent: the food database is a shared catalogue and
 * local food rows carry no userId at all, so there is nothing to scope them by.
 * Sign-out still wipes it along with everything else.
 */
export const USER_OWNED_TABLES = [
  'dailyLogs',
  'activities',
  'meals',
  'measurements',
  'photos',
  'dailyNutrition',
] as const;

/** Workbox runtime cache holding the raw photo bytes (see vite.config.ts). */
export const PROGRESS_PHOTO_CACHE = 'progress-photos';

/**
 * Decide whether rows/queue entries with no `userId` can be adopted by the
 * cached account during the v5 upgrade.
 *
 * Untagged rows are ambiguous by construction: before this version only the
 * cold-start hydration stamped an owner, so every row written by a background
 * revalidation or a local save came out with `userId === undefined`. On a
 * single-account browser they are obviously that account's, and adopting them
 * keeps the app from looking empty after the upgrade. On a browser that has
 * seen two accounts there is no way to tell whose they are, so they stay
 * untagged — which, under the new read filter, means invisible to everyone
 * until the server re-confirms them and the merge stamps the real owner.
 *
 * `distinctUserIds` is every non-null userId present in the local DB.
 */
export function shouldAdoptUntaggedRows(
  distinctUserIds: number[],
  cachedUserId?: number
): boolean {
  if (cachedUserId == null) return false;
  return distinctUserIds.every((id) => id === cachedUserId);
}

type SyncedRow = DedupeCandidate;

/**
 * Return the localIds of rows that duplicate another row's serverId.
 *
 * One server row must map to exactly one local row. Older merge logic could
 * insert a second copy under a fresh localId, which is how a browser ends up
 * rendering the same activity twice. `preferRow` picks the survivor — with
 * every candidate carrying a serverId that reduces to the lowest localId.
 *
 * Rows with a null serverId are never returned: those are local creates that
 * have not been pushed yet, so the local DB is their only copy. `findDuplicate-
 * DateIds` cannot do this job — it matches by date, and `activities` legitimately
 * holds many rows per date.
 */
export function findDuplicateServerIds(rows: SyncedRow[]): number[] {
  const keptByServerId = new Map<number, SyncedRow>();
  const toDelete: number[] = [];

  for (const row of rows) {
    if (row.serverId == null || row.localId == null) continue;

    const kept = keptByServerId.get(row.serverId);
    if (kept == null) {
      keptByServerId.set(row.serverId, row);
      continue;
    }
    const winner = preferRow(kept, row);
    const loser = winner === kept ? row : kept;
    keptByServerId.set(row.serverId, winner);
    if (loser.localId != null) toDelete.push(loser.localId);
  }

  return toDelete;
}

// ── Database class ───────────────────────────────────────────────────────────

class AskesisDB extends Dexie {
  dailyLogs!: Table<LocalDailyLog, number>;
  activities!: Table<LocalActivity, number>;
  meals!: Table<LocalMeal, number>;
  foods!: Table<LocalFood, number>;
  measurements!: Table<LocalMeasurement, number>;
  photos!: Table<LocalPhoto, number>;
  dailyNutrition!: Table<LocalDailyNutrition, number>;
  settings!: Table<LocalSetting, string>;
  pendingSync!: Table<PendingSyncEntry, number>;

  constructor() {
    super('askesis');

    // ── Version 1: Initial schema ──────────────────────────────────────────
    this.version(1).stores({
      dailyLogs: '++localId, serverId, date, userId, updatedAt',
      activities: '++localId, serverId, date, userId, updatedAt',
      meals: '++localId, serverId, date, userId, updatedAt',
      foods: '++localId, serverId, name, updatedAt',
      measurements: '++localId, serverId, date, userId, updatedAt',
      settings: 'key',
      pendingSync: '++id, table, operation, localId, serverId, timestamp',
    });

    // ── Version 2: Add photos table ────────────────────────────────────────
    this.version(2).stores({
      dailyLogs: '++localId, serverId, date, userId, updatedAt',
      activities: '++localId, serverId, date, userId, updatedAt',
      meals: '++localId, serverId, date, userId, updatedAt',
      foods: '++localId, serverId, name, updatedAt',
      measurements: '++localId, serverId, date, userId, updatedAt',
      photos: '++localId, serverId, date, userId, view, updatedAt',
      settings: 'key',
      pendingSync: '++id, table, operation, localId, serverId, timestamp',
    });

    // ── Version 3: Add dailyNutrition table ────────────────────────────────
    this.version(3)
      .stores({
        dailyLogs: '++localId, serverId, date, userId, updatedAt',
        activities: '++localId, serverId, date, userId, updatedAt',
        meals: '++localId, serverId, date, userId, updatedAt',
        foods: '++localId, serverId, name, updatedAt',
        measurements: '++localId, serverId, date, userId, updatedAt',
        photos: '++localId, serverId, date, userId, view, updatedAt',
        dailyNutrition: '++localId, serverId, date, userId, updatedAt',
        settings: 'key',
        pendingSync: '++id, table, operation, localId, serverId, timestamp',
      })
      .upgrade(async (tx) => {
        // One-shot cleanup of duplicate-by-date rows stranded by older sync
        // bugs. This used to run on every mount; do it once, here, and record
        // it so the runtime path can skip the table scan forever after.
        for (const name of ['dailyLogs', 'measurements'] as const) {
          const table = tx.table(name);
          const rows = await table.toArray();
          const duplicates = findDuplicateDateIds(rows);
          if (duplicates.length > 0) {
            await table.bulkDelete(duplicates);
          }
        }
        await tx.table('settings').put({ key: DEDUPE_BY_DATE_FLAG, value: true });
      });

    // ── Version 4: dedupe by serverId across every synced table ────────────
    // Same stores as v3 — this version exists only to run the upgrade.
    this.version(4)
      .stores({
        dailyLogs: '++localId, serverId, date, userId, updatedAt',
        activities: '++localId, serverId, date, userId, updatedAt',
        meals: '++localId, serverId, date, userId, updatedAt',
        foods: '++localId, serverId, name, updatedAt',
        measurements: '++localId, serverId, date, userId, updatedAt',
        photos: '++localId, serverId, date, userId, view, updatedAt',
        dailyNutrition: '++localId, serverId, date, userId, updatedAt',
        settings: 'key',
        pendingSync: '++id, table, operation, localId, serverId, timestamp',
      })
      .upgrade(async (tx) => {
        // The v3 cleanup only covered dailyLogs + measurements and only matched
        // by date, so it could never reach a duplicate-by-serverId in a
        // many-rows-per-date table like `activities` — browsers upgraded to v3
        // still show the same workout twice. Sweep every synced table by
        // serverId instead. Unsynced rows (serverId == null) are left alone;
        // this DB is the only place they exist.
        for (const name of SYNCED_TABLES) {
          const table = tx.table(name);
          const duplicates = findDuplicateServerIds(await table.toArray());
          if (duplicates.length > 0) {
            await table.bulkDelete(duplicates);
          }
        }
      });

    // ── Version 5: own every row and queue entry by userId ─────────────────
    // Only `pendingSync` changes shape (a userId index); the rest are carried
    // forward unchanged so the upgrade can run.
    this.version(5)
      .stores({
        dailyLogs: '++localId, serverId, date, userId, updatedAt',
        activities: '++localId, serverId, date, userId, updatedAt',
        meals: '++localId, serverId, date, userId, updatedAt',
        foods: '++localId, serverId, name, updatedAt',
        measurements: '++localId, serverId, date, userId, updatedAt',
        photos: '++localId, serverId, date, userId, view, updatedAt',
        dailyNutrition: '++localId, serverId, date, userId, updatedAt',
        settings: 'key',
        pendingSync: '++id, table, operation, localId, serverId, timestamp, userId',
      })
      .upgrade(async (tx) => {
        // Reads are now filtered by userId, and a row that never got one would
        // be invisible. Adopt those rows for the cached account, but only when
        // this browser shows no evidence of a second account — see
        // `shouldAdoptUntaggedRows`. Never guess on a shared browser: guessing
        // wrong is exactly the cross-user leak this version exists to close.
        const cached = await tx.table('settings').get('cachedUser');
        const cachedUserId = (cached?.value as { id?: number } | undefined)?.id;

        const seen = new Set<number>();
        for (const name of USER_OWNED_TABLES) {
          for (const row of await tx.table(name).toArray()) {
            if (row.userId != null) seen.add(row.userId);
          }
        }
        for (const entry of await tx.table('pendingSync').toArray()) {
          if (entry.userId != null) seen.add(entry.userId);
        }

        if (!shouldAdoptUntaggedRows([...seen], cachedUserId)) return;

        for (const name of USER_OWNED_TABLES) {
          const table = tx.table(name);
          const untagged = (await table.toArray()).filter((r) => r.userId == null);
          if (untagged.length > 0) {
            await table.bulkPut(untagged.map((r) => ({ ...r, userId: cachedUserId })));
          }
        }
        // Queue entries too: an untagged entry is only pushable while it can be
        // attributed, and on a single-account browser it is that account's.
        const queue = tx.table('pendingSync');
        const untaggedQueue = (await queue.toArray()).filter((e) => e.userId == null);
        if (untaggedQueue.length > 0) {
          await queue.bulkPut(untaggedQueue.map((e) => ({ ...e, userId: cachedUserId })));
        }
      });

    // ── Future versions go here ────────────────────────────────────────────
  }
}

export const db = new AskesisDB();

/**
 * Erase every trace of the signed-in account from this device.
 *
 * Called on sign-out. Everything in this database is per-account — the synced
 * tables, the cached identity, the cached user settings and the sync cursor —
 * so the whole database goes, along with the service worker's photo cache,
 * which holds the raw image bytes and would otherwise still serve them to
 * whoever signs in next.
 *
 * `keepPendingSync` preserves the offline mutation queue, which is the only
 * copy of work that never reached the server. Kept entries stay tagged with
 * the account that made them and are pushed only when that account signs back
 * in (see `flushPendingSync`), so keeping them cannot leak into another
 * account. The caller decides; nothing here discards queued work implicitly.
 */
export async function clearLocalUserData(keepPendingSync = false): Promise<void> {
  const preserved = keepPendingSync ? await db.pendingSync.toArray() : [];

  await Promise.all(db.tables.map((table) => table.clear()));

  if (preserved.length > 0) {
    await db.pendingSync.bulkAdd(preserved);
  }

  if (typeof caches !== 'undefined') {
    try {
      await caches.delete(PROGRESS_PHOTO_CACHE);
    } catch {
      // Best effort — a Cache Storage failure must not block sign-out.
    }
  }
}
