/**
 * Offline-aware data access layer backed by Dexie.
 *
 * Provides the same method signatures as the existing api client but:
 * - Reads return Dexie data instantly (works offline) and revalidate in the
 *   background: the server fetch is fire-and-forget, merges into Dexie, and
 *   bumps `dataVersion` only if the merge actually changed something
 * - Writes go to Dexie first (instant UI update), then sync to server
 * - If server write succeeds, updates serverId in Dexie
 * - If server write fails (offline), queues in pendingSync
 *
 * Components subscribe to `dataVersion` to re-read after a background
 * revalidation lands:  `$: if ($dataVersion !== seen) { seen = $dataVersion; reload(); }`
 *
 * IMPORTANT: reads scoped to another user (`_userId` truthy — the "shared with
 * me" case) bypass Dexie entirely. The local DB only ever holds the current
 * user's rows, so serving them for someone else's id would show the wrong data.
 *
 * Components can gradually migrate from `api.*` to `offlineApi.*` calls.
 * The return types match the existing API types so no component changes needed.
 */

import { writable } from 'svelte/store';
import { type Table } from 'dexie';
import {
  db,
  findDuplicateDateIds,
  DEDUPE_BY_DATE_FLAG,
  type LocalDailyLog,
  type LocalActivity,
  type LocalMeal,
  type LocalMeasurement,
  type LocalPhoto,
  type LocalDailyNutrition,
} from '$lib/db';
import {
  api,
  type DailyLog,
  type DailyLogInput,
  type Activity,
  type ActivityInput,
  type Meal,
  type MealInput,
  type FoodItem,
  type BodyMeasurement,
  type BodyMeasurementInput,
  type DailyNutrition,
  type DailyNutritionInput,
  type ProgressPhoto,
  type PhotoView,
} from '$lib/api/client';
import { queueSync } from '$lib/sync';

// ── Helpers ──────────────────────────────────────────────────────────────────

function now(): string {
  return new Date().toISOString();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UpdateSpec = Record<string, any>;

// ── Background revalidation ──────────────────────────────────────────────────

/**
 * Bumped once per background revalidation that actually wrote to Dexie.
 * Never bumped when the server returned data identical to the cache, which is
 * what keeps `$: $dataVersion → reload()` from looping forever.
 */
export const dataVersion = writable(0);

/** Revalidations currently running, keyed by table + query params. */
const inFlight = new Set<string>();

/** When each key last started a revalidation, so a reload triggered by a
 *  `dataVersion` bump doesn't immediately re-fetch what just landed. */
const lastRevalidated = new Map<string, number>();
const REVALIDATE_MIN_INTERVAL_MS = 2000;

/** Merges that land together (cold start hydrates several tables at once)
 *  collapse into a single bump instead of N re-reads. */
const BUMP_COALESCE_MS = 50;
let bumpTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * All Dexie merges run one at a time. The fetches stay parallel; only the
 * read-modify-write is serialized, so two concurrent revalidations (or a
 * revalidation racing initial hydration) can't both decide a row is missing
 * and insert it twice.
 */
let mergeChain: Promise<unknown> = Promise.resolve();

function serializeMerge<T>(fn: () => Promise<T>): Promise<T> {
  const next = mergeChain.then(fn, fn);
  mergeChain = next.catch(() => {});
  return next;
}

function bumpDataVersion(): void {
  if (bumpTimer !== null) return;
  bumpTimer = setTimeout(() => {
    bumpTimer = null;
    dataVersion.update((n) => n + 1);
  }, BUMP_COALESCE_MS);
}

/**
 * Fire-and-forget background refresh. Deduplicated by `key` so rapid
 * navigation doesn't stack N identical fetches. Failures are silent — being
 * offline is the normal case — and never clear cached data.
 */
function revalidate(key: string, task: () => Promise<boolean>): void {
  if (inFlight.has(key)) return;
  if (Date.now() - (lastRevalidated.get(key) ?? 0) < REVALIDATE_MIN_INTERVAL_MS) return;

  inFlight.add(key);
  lastRevalidated.set(key, Date.now());

  task()
    .then((changed) => {
      if (changed) bumpDataVersion();
    })
    .catch(() => {
      // Offline or server error: keep serving the cache.
    })
    .finally(() => {
      inFlight.delete(key);
    });
}

/** Drop keys whose value is `undefined` so Dexie never deletes a field we
 *  simply didn't map (e.g. `userId` when the caller didn't pass one). Server
 *  fields that were genuinely cleared come back as `null`, which is kept. */
function stripUndefined(spec: UpdateSpec): UpdateSpec {
  const out: UpdateSpec = {};
  for (const [key, value] of Object.entries(spec)) {
    if (value !== undefined) out[key] = value;
  }
  return out;
}

/** True if applying `spec` to `existing` would change anything meaningful.
 *  `updatedAt` is ignored — it is regenerated on every fetch by design. */
function specDiffers(existing: Record<string, unknown>, spec: UpdateSpec): boolean {
  for (const [key, value] of Object.entries(spec)) {
    if (key === 'updatedAt') continue;
    const current = existing[key];
    if (current === value) continue;
    if (current == null && value == null) continue;
    if ((current !== null && typeof current === 'object') || (value !== null && typeof value === 'object')) {
      if (JSON.stringify(current ?? null) !== JSON.stringify(value ?? null)) return true;
      continue;
    }
    return true;
  }
  return false;
}

/**
 * Merge a page of server rows into a Dexie table with a single indexed lookup
 * (`anyOf`) instead of one `.first()` per row, and a single bulk write.
 *
 * Returns true only if rows were inserted or changed, which is the signal the
 * UI listens to.
 */
async function mergeServerRows<T>(
  /** Dexie table name — also the key `pendingSync` rows are filed under. */
  tableName: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table: Table<any, number>,
  rows: T[],
  getId: (row: T) => number,
  toLocal: (row: T) => UpdateSpec,
  /** For one-row-per-date tables: adopt an unsynced local row for the same
   *  date instead of inserting a duplicate next to it. */
  matchByDate = false
): Promise<boolean> {
  if (rows.length === 0) return false;

  const specs = rows.map((row) => ({ id: getId(row), spec: stripUndefined(toLocal(row)) }));
  const ids = specs.map((s) => s.id);

  // Rows with an unflushed local mutation are never overwritten — the user's
  // offline edit is newer than anything the server can currently return.
  const pending = await db.pendingSync.where('table').equals(tableName).toArray();
  const pendingLocalIds = new Set(pending.map((p) => p.localId));

  const existingRows = await table.where('serverId').anyOf(ids).toArray();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const byServerId = new Map<number, any>();
  for (const row of existingRows) byServerId.set(row.serverId, row);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const orphansByDate = new Map<string, any>();
  if (matchByDate) {
    const dates = specs.map((s) => s.spec.date).filter((d): d is string => typeof d === 'string');
    if (dates.length > 0) {
      const dateRows = await table.where('date').anyOf(dates).toArray();
      for (const row of dateRows) {
        if (row.serverId == null && !orphansByDate.has(row.date)) orphansByDate.set(row.date, row);
      }
    }
  }

  const inserts: UpdateSpec[] = [];
  const updates: UpdateSpec[] = [];

  for (const { id, spec } of specs) {
    let existing = byServerId.get(id);
    if (!existing && matchByDate && typeof spec.date === 'string') {
      const orphan = orphansByDate.get(spec.date);
      if (orphan) {
        // An unsynced local row owns this date: leave it alone entirely, and
        // don't insert a second row next to it. The push will reconcile it and
        // a later revalidation will adopt it once it has a serverId.
        orphansByDate.delete(spec.date);
        if (pendingLocalIds.has(orphan.localId)) continue;
        existing = orphan;
      }
    }

    if (!existing) {
      inserts.push({ ...spec, serverId: id });
      continue;
    }

    if (pendingLocalIds.has(existing.localId)) continue;

    if (existing.serverId !== id || specDiffers(existing, spec)) {
      updates.push({ ...existing, ...spec, serverId: id, updatedAt: now() });
    }
  }

  if (inserts.length > 0) await table.bulkAdd(inserts);
  if (updates.length > 0) await table.bulkPut(updates);

  return inserts.length > 0 || updates.length > 0;
}

/** Convert a server DailyLog to local format */
function toLocalDailyLog(log: DailyLog, userId?: number): UpdateSpec {
  return {
    serverId: log.id,
    date: log.date,
    userId,
    weight: log.weight,
    sleep_hours: log.sleep_hours,
    steps: log.steps,
    water_ml: log.water_ml,
    feelings: log.feelings,
    caffeine_mg: log.caffeine_mg,
    ate_outside: log.ate_outside,
    notes: log.notes,
    updatedAt: now(),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromLocalDailyLog(local: any): DailyLog {
  return {
    id: local.serverId ?? local.localId!,
    date: local.date,
    weight: local.weight,
    sleep_hours: local.sleep_hours,
    steps: local.steps,
    water_ml: local.water_ml,
    feelings: local.feelings,
    caffeine_mg: local.caffeine_mg,
    ate_outside: local.ate_outside,
    notes: local.notes,
  };
}

function toLocalActivity(activity: Activity, userId?: number): UpdateSpec {
  return {
    serverId: activity.id,
    date: activity.date,
    userId,
    name: activity.name,
    activity_type: activity.activity_type,
    time_of_day: activity.time_of_day,
    duration_mins: activity.duration_mins,
    calories: activity.calories,
    distance_km: activity.distance_km,
    url: activity.url,
    notes: activity.notes,
    tags: activity.tags,
    icon: activity.icon,
    exercises: activity.exercises,
    updatedAt: now(),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromLocalActivity(local: any): Activity {
  return {
    id: local.serverId ?? local.localId!,
    date: local.date,
    name: local.name,
    activity_type: local.activity_type,
    time_of_day: local.time_of_day as Activity['time_of_day'],
    duration_mins: local.duration_mins,
    calories: local.calories,
    distance_km: local.distance_km,
    url: local.url,
    notes: local.notes,
    tags: local.tags,
    icon: local.icon,
    exercises: local.exercises,
  };
}

function toLocalMeal(meal: Meal, userId?: number): UpdateSpec {
  return {
    serverId: meal.id,
    date: meal.date,
    userId,
    label: meal.label,
    time: meal.time,
    calories: meal.calories,
    description: meal.description,
    photo_path: meal.photo_path,
    drive_file_id: meal.drive_file_id,
    ai_analysis: meal.ai_analysis,
    photo_url: meal.photo_url,
    food_items: meal.food_items,
    computed_calories: meal.computed_calories,
    computed_protein_g: meal.computed_protein_g,
    computed_carbs_g: meal.computed_carbs_g,
    computed_fat_g: meal.computed_fat_g,
    updatedAt: now(),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromLocalMeal(local: any): Meal {
  return {
    id: local.serverId ?? local.localId!,
    date: local.date,
    label: local.label,
    time: local.time,
    calories: local.calories,
    description: local.description,
    photo_path: local.photo_path,
    drive_file_id: local.drive_file_id,
    ai_analysis: local.ai_analysis,
    photo_url: local.photo_url,
    food_items: local.food_items,
    computed_calories: local.computed_calories,
    computed_protein_g: local.computed_protein_g,
    computed_carbs_g: local.computed_carbs_g,
    computed_fat_g: local.computed_fat_g,
  };
}

function toLocalMeasurement(m: BodyMeasurement, userId?: number): UpdateSpec {
  return {
    serverId: m.id,
    date: m.date,
    userId,
    neck: m.neck,
    shoulders: m.shoulders,
    chest: m.chest,
    bicep_left: m.bicep_left,
    bicep_right: m.bicep_right,
    forearm_left: m.forearm_left,
    forearm_right: m.forearm_right,
    waist: m.waist,
    abdomen: m.abdomen,
    hips: m.hips,
    thigh_left: m.thigh_left,
    thigh_right: m.thigh_right,
    calf_left: m.calf_left,
    calf_right: m.calf_right,
    notes: m.notes,
    updatedAt: now(),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromLocalMeasurement(local: any): BodyMeasurement {
  return {
    id: local.serverId ?? local.localId!,
    date: local.date,
    neck: local.neck,
    shoulders: local.shoulders,
    chest: local.chest,
    bicep_left: local.bicep_left,
    bicep_right: local.bicep_right,
    forearm_left: local.forearm_left,
    forearm_right: local.forearm_right,
    waist: local.waist,
    abdomen: local.abdomen,
    hips: local.hips,
    thigh_left: local.thigh_left,
    thigh_right: local.thigh_right,
    calf_left: local.calf_left,
    calf_right: local.calf_right,
    notes: local.notes,
  };
}

function toLocalNutrition(n: DailyNutrition, userId?: number): UpdateSpec {
  return {
    serverId: n.id,
    date: n.date,
    userId: userId ?? n.user_id,
    protein_g: n.protein_g,
    carbs_g: n.carbs_g,
    fat_g: n.fat_g,
    notes: n.notes,
    updatedAt: now(),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromLocalNutrition(local: any): DailyNutrition {
  return {
    id: local.serverId ?? local.localId ?? 0,
    user_id: local.userId ?? local.user_id ?? 0,
    date: local.date,
    protein_g: local.protein_g,
    carbs_g: local.carbs_g,
    fat_g: local.fat_g,
    notes: local.notes,
  };
}

function toLocalFood(f: FoodItem): UpdateSpec {
  return {
    serverId: f.id,
    name: f.name,
    brand: f.brand,
    category: f.category,
    serving_size: f.serving_size,
    serving_unit: f.serving_unit,
    calories: f.calories,
    protein_g: f.protein_g,
    carbs_g: f.carbs_g,
    fat_g: f.fat_g,
    fiber_g: f.fiber_g,
    is_shared: f.is_shared,
    source: f.source,
    updatedAt: now(),
  };
}

function toLocalPhoto(p: ProgressPhoto, userId?: number): UpdateSpec {
  return {
    serverId: p.id,
    date: p.date,
    userId,
    view: p.view,
    drive_file_id: p.drive_file_id,
    notes: p.notes,
    url: p.url,
    updatedAt: now(),
  };
}

function localToPhoto(p: LocalPhoto): ProgressPhoto {
  return {
    id: p.serverId ?? p.localId!,
    date: p.date,
    view: p.view,
    drive_file_id: p.drive_file_id,
    notes: p.notes,
    url: p.url || api.getPhotoUrl(p.serverId ?? p.localId!),
  };
}

// ── Hydrate: populate Dexie from server on first load ────────────────────────

async function hydrateTable<T>(
  tableName: string,
  fetcher: () => Promise<T[]>,
  getId: (item: T) => number,
  toLocal: (item: T) => UpdateSpec,
  matchByDate = false
): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const table = (db as any)[tableName];
  const localCount = await table.count();
  if (localCount > 0) return; // Already hydrated

  try {
    const serverData = await fetcher();
    const changed = await serializeMerge(() =>
      mergeServerRows(tableName, table, serverData, getId, toLocal, matchByDate)
    );
    if (changed) bumpDataVersion();
  } catch (err) {
    console.warn(`[askesis] Failed to hydrate ${tableName}:`, err);
  }
}

/**
 * Remove duplicate records for the same date, keeping the one with a serverId.
 *
 * This is a one-shot repair for duplicates stranded by older sync bugs, not a
 * per-mount maintenance task — it scans the whole table. `runOneShotDedupe`
 * guards it; the v3 Dexie upgrade does the same work for anyone migrating.
 */
async function deduplicateByDate(tableName: string): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const table = (db as any)[tableName];
  const all = await table.toArray();
  const toDelete = findDuplicateDateIds(all);

  if (toDelete.length > 0) {
    await table.bulkDelete(toDelete);
  }
}

/** Run the date-duplicate cleanup at most once per browser profile. */
async function runOneShotDedupe(): Promise<void> {
  try {
    const flag = await db.settings.get(DEDUPE_BY_DATE_FLAG);
    if (flag?.value) return;

    await Promise.all([deduplicateByDate('dailyLogs'), deduplicateByDate('measurements')]);
    await db.settings.put({ key: DEDUPE_BY_DATE_FLAG, value: true });
  } catch (err) {
    console.warn('[askesis] Duplicate cleanup failed:', err);
  }
}

export async function hydrateFromServer(userId?: number): Promise<void> {
  // Clean up duplicates left behind by prior sync issues (once, ever)
  await runOneShotDedupe();

  // Use max server limit (500) to get complete data for offline use
  await Promise.all([
    hydrateTable('dailyLogs', () => api.getDailyLogs(undefined, undefined, undefined, 500), (log) => log.id, (log) => toLocalDailyLog(log, userId), true),
    hydrateTable('activities', () => api.getActivities(undefined, undefined, undefined, 500), (a) => a.id, (a) => toLocalActivity(a, userId)),
    hydrateTable('meals', () => api.getMeals(undefined, undefined, undefined, undefined, 500), (m) => m.id, (m) => toLocalMeal(m, userId)),
    hydrateTable('foods', () => api.searchFoods(undefined, undefined, false, 200), (f) => f.id, toLocalFood),
    hydrateTable('measurements', () => api.getMeasurements(undefined, undefined, undefined), (m) => m.id, (m) => toLocalMeasurement(m, userId), true),
    hydrateTable('photos', () => api.getPhotos(undefined, undefined, undefined, undefined), (p) => p.id, (p) => toLocalPhoto(p, userId)),
    hydrateTable('dailyNutrition', () => api.getNutritionHistory(undefined, undefined, undefined, 500), (n) => n.id, (n) => toLocalNutrition(n, userId), true),
  ]);
}

// ── Offline-aware API ────────────────────────────────────────────────────────
// Each method: read from Dexie → return local data → background-refresh from server

export const offlineApi = {
  // ── Daily Logs ───────────────────────────────────────────────────────────

  async getDailyLogs(
    startDate?: string,
    endDate?: string,
    _userId?: number,
    limit?: number
  ): Promise<DailyLog[]> {
    // Another user's data is never in the local DB — go straight to the server
    if (_userId) return api.getDailyLogs(startDate, endDate, _userId, limit);

    revalidate(`dailyLogs:${startDate ?? ''}:${endDate ?? ''}:${limit ?? ''}`, async () => {
      const serverLogs = await api.getDailyLogs(startDate, endDate, undefined, limit);
      return serializeMerge(() =>
        mergeServerRows('dailyLogs', db.dailyLogs, serverLogs, (log) => log.id, (log) => toLocalDailyLog(log), true)
      );
    });

    // Serve from Dexie immediately
    let collection = db.dailyLogs.orderBy('date').reverse();

    if (startDate && endDate) {
      collection = db.dailyLogs.where('date').between(startDate, endDate, true, true).reverse();
    }

    let results = await collection.toArray();

    // Deduplicate by date (keep the one with serverId, or the latest localId)
    const byDate = new Map<string, LocalDailyLog>();
    for (const r of results) {
      const existing = byDate.get(r.date);
      if (!existing || (r.serverId && !existing.serverId) || (r.localId! > existing.localId!)) {
        byDate.set(r.date, r);
      }
    }
    results = [...byDate.values()].sort((a, b) => b.date.localeCompare(a.date));

    if (limit) results = results.slice(0, limit);
    return results.map(fromLocalDailyLog);
  },

  async getDailyLog(date: string, _userId?: number): Promise<DailyLog> {
    const local = await db.dailyLogs.where('date').equals(date).first();
    if (local) {
      return fromLocalDailyLog(local);
    }

    const serverLog = await api.getDailyLog(date, _userId);
    await db.dailyLogs.add(toLocalDailyLog(serverLog) as LocalDailyLog);
    return serverLog;
  },

  async saveDailyLog(data: DailyLogInput): Promise<DailyLog> {
    // Write to Dexie first
    const existing = await db.dailyLogs.where('date').equals(data.date).first();
    const localRecord: LocalDailyLog = {
      ...data,
      updatedAt: now(),
    };

    let localId: number;
    if (existing) {
      await db.dailyLogs.update(existing.localId!, localRecord as UpdateSpec);
      localId = existing.localId!;
    } else {
      localId = await db.dailyLogs.add(localRecord);
    }

    // Try server sync
    try {
      const serverLog = await api.saveDailyLog(data);
      await db.dailyLogs.update(localId, { serverId: serverLog.id });
      return serverLog;
    } catch {
      // Queue for later sync
      await queueSync('dailyLogs', existing ? 'update' : 'create', localId, existing?.serverId, data as unknown as Record<string, unknown>);
      return fromLocalDailyLog({ ...localRecord, localId });
    }
  },

  // ── Activities ───────────────────────────────────────────────────────────

  async getActivities(
    startDate?: string,
    endDate?: string,
    _userId?: number,
    limit?: number
  ): Promise<Activity[]> {
    if (_userId) return api.getActivities(startDate, endDate, _userId, limit);

    revalidate(`activities:${startDate ?? ''}:${endDate ?? ''}:${limit ?? ''}`, async () => {
      const serverActivities = await api.getActivities(startDate, endDate, undefined, limit);
      return serializeMerge(() =>
        mergeServerRows('activities', db.activities, serverActivities, (a) => a.id, (a) => toLocalActivity(a))
      );
    });

    // Serve from Dexie immediately
    let results: LocalActivity[];

    if (startDate && endDate) {
      results = await db.activities.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.activities.orderBy('date').reverse().toArray();
    }

    if (limit) results = results.slice(0, limit);
    return results.map(fromLocalActivity);
  },

  async createActivity(data: ActivityInput): Promise<Activity> {
    const localRecord: LocalActivity = {
      ...data,
      exercises: data.exercises || [],
      updatedAt: now(),
    };
    const localId = await db.activities.add(localRecord);

    try {
      const serverActivity = await api.createActivity(data);
      await db.activities.update(localId, { serverId: serverActivity.id });
      return serverActivity;
    } catch {
      await queueSync('activities', 'create', localId, undefined, data as unknown as Record<string, unknown>);
      return fromLocalActivity({ ...localRecord, localId });
    }
  },

  async updateActivity(id: number, data: ActivityInput): Promise<Activity> {
    // id could be serverId or localId
    const existing = await db.activities.where('serverId').equals(id).first()
      ?? await db.activities.get(id);

    if (existing) {
      await db.activities.update(existing.localId!, { ...data, exercises: data.exercises || [], updatedAt: now() } as UpdateSpec);
    }

    try {
      const serverActivity = await api.updateActivity(id, data);
      if (existing) {
        await db.activities.update(existing.localId!, { serverId: serverActivity.id } as UpdateSpec);
      }
      return serverActivity;
    } catch {
      if (existing) {
        await queueSync('activities', 'update', existing.localId!, existing.serverId, data as unknown as Record<string, unknown>);
        return fromLocalActivity({ ...existing, ...data, exercises: data.exercises || [], updatedAt: now() });
      }
      throw new Error('Activity not found locally and server unavailable');
    }
  },

  async deleteActivity(id: number): Promise<void> {
    const existing = await db.activities.where('serverId').equals(id).first()
      ?? await db.activities.get(id);

    if (existing) {
      await db.activities.delete(existing.localId!);
    }

    try {
      await api.deleteActivity(id);
    } catch {
      if (existing) {
        await queueSync('activities', 'delete', existing.localId!, existing.serverId);
      }
    }
  },

  // ── Meals ────────────────────────────────────────────────────────────────

  async getMeals(
    date?: string,
    _userId?: number,
    startDate?: string,
    endDate?: string,
    limit?: number
  ): Promise<Meal[]> {
    if (_userId) return api.getMeals(date, _userId, startDate, endDate, limit);

    revalidate(`meals:${date ?? ''}:${startDate ?? ''}:${endDate ?? ''}:${limit ?? ''}`, async () => {
      const serverMeals = await api.getMeals(date, undefined, startDate, endDate, limit);
      return serializeMerge(() =>
        mergeServerRows('meals', db.meals, serverMeals, (m) => m.id, (m) => toLocalMeal(m))
      );
    });

    // Serve from Dexie immediately
    let results: LocalMeal[];

    if (date) {
      results = await db.meals.where('date').equals(date).toArray();
    } else if (startDate && endDate) {
      results = await db.meals.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.meals.orderBy('date').reverse().toArray();
    }

    if (limit) results = results.slice(0, limit);
    return results.map(fromLocalMeal);
  },

  async createMeal(data: MealInput): Promise<Meal> {
    const localRecord: LocalMeal = {
      date: data.date,
      label: data.label,
      time: data.time,
      calories: data.calories,
      description: data.description,
      updatedAt: now(),
    };
    const localId = await db.meals.add(localRecord);

    try {
      const serverMeal = await api.createMeal(data);
      await db.meals.update(localId, toLocalMeal(serverMeal));
      return serverMeal;
    } catch {
      await queueSync('meals', 'create', localId, undefined, data as unknown as Record<string, unknown>);
      return fromLocalMeal({ ...localRecord, localId });
    }
  },

  async updateMeal(id: number, data: MealInput): Promise<Meal> {
    const existing = await db.meals.where('serverId').equals(id).first()
      ?? await db.meals.get(id);

    if (existing) {
      await db.meals.update(existing.localId!, { ...data, updatedAt: now() } as UpdateSpec);
    }

    try {
      const serverMeal = await api.updateMeal(id, data);
      if (existing) {
        await db.meals.update(existing.localId!, toLocalMeal(serverMeal));
      }
      return serverMeal;
    } catch {
      if (existing) {
        await queueSync('meals', 'update', existing.localId!, existing.serverId, data as unknown as Record<string, unknown>);
        return fromLocalMeal({ ...existing, ...data, updatedAt: now() });
      }
      throw new Error('Meal not found locally and server unavailable');
    }
  },

  async deleteMeal(id: number): Promise<void> {
    const existing = await db.meals.where('serverId').equals(id).first()
      ?? await db.meals.get(id);

    if (existing) {
      await db.meals.delete(existing.localId!);
    }

    try {
      await api.deleteMeal(id);
    } catch {
      if (existing) {
        await queueSync('meals', 'delete', existing.localId!, existing.serverId);
      }
    }
  },

  // ── Measurements ─────────────────────────────────────────────────────────

  async getMeasurements(
    startDate?: string,
    endDate?: string,
    _userId?: number
  ): Promise<BodyMeasurement[]> {
    if (_userId) return api.getMeasurements(startDate, endDate, _userId);

    revalidate(`measurements:${startDate ?? ''}:${endDate ?? ''}`, async () => {
      const serverMeasurements = await api.getMeasurements(startDate, endDate, undefined);
      return serializeMerge(() =>
        mergeServerRows('measurements', db.measurements, serverMeasurements, (m) => m.id, (m) => toLocalMeasurement(m), true)
      );
    });

    // Serve from Dexie immediately
    let results: LocalMeasurement[];

    if (startDate && endDate) {
      results = await db.measurements.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.measurements.orderBy('date').reverse().toArray();
    }

    return results.map(fromLocalMeasurement);
  },

  async getMeasurement(date: string, _userId?: number): Promise<BodyMeasurement> {
    const local = await db.measurements.where('date').equals(date).first();
    if (local) {
      return fromLocalMeasurement(local);
    }

    const server = await api.getMeasurement(date, _userId);
    await db.measurements.add(toLocalMeasurement(server) as LocalMeasurement);
    return server;
  },

  async saveMeasurement(data: BodyMeasurementInput): Promise<BodyMeasurement> {
    const existing = await db.measurements.where('date').equals(data.date).first();
    const localRecord: LocalMeasurement = { ...data, updatedAt: now() };

    let localId: number;
    if (existing) {
      await db.measurements.update(existing.localId!, localRecord as UpdateSpec);
      localId = existing.localId!;
    } else {
      localId = await db.measurements.add(localRecord);
    }

    try {
      const server = await api.saveMeasurement(data);
      await db.measurements.update(localId, { serverId: server.id });
      return server;
    } catch {
      await queueSync('measurements', existing ? 'update' : 'create', localId, existing?.serverId, data as unknown as Record<string, unknown>);
      return fromLocalMeasurement({ ...localRecord, localId });
    }
  },

  async deleteMeasurement(id: number): Promise<void> {
    const existing = await db.measurements.where('serverId').equals(id).first()
      ?? await db.measurements.get(id);

    if (existing) {
      await db.measurements.delete(existing.localId!);
    }

    try {
      await api.deleteMeasurement(id);
    } catch {
      if (existing) {
        await queueSync('measurements', 'delete', existing.localId!, existing.serverId);
      }
    }
  },

  // ── Nutrition ────────────────────────────────────────────────────────────

  async getDailyNutrition(date: string, userId?: number): Promise<DailyNutrition> {
    if (userId) return api.getDailyNutrition(date, userId);

    const local = await db.dailyNutrition.where('date').equals(date).first();

    if (local) {
      revalidate(`dailyNutritionDate:${date}`, async () => {
        const server = await api.getDailyNutrition(date, undefined);
        return serializeMerge(() =>
          mergeServerRows('dailyNutrition', db.dailyNutrition, [server], (n) => n.id, (n) => toLocalNutrition(n), true)
        );
      });
      return fromLocalNutrition(local);
    }

    try {
      const server = await api.getDailyNutrition(date, undefined);
      await serializeMerge(() =>
        mergeServerRows('dailyNutrition', db.dailyNutrition, [server], (n) => n.id, (n) => toLocalNutrition(n), true)
      );
      return server;
    } catch {
      // Nothing cached and nothing on the server (or we're offline)
      return { id: 0, user_id: 0, date } as DailyNutrition;
    }
  },

  async saveDailyNutrition(data: DailyNutritionInput): Promise<DailyNutrition> {
    // Write to Dexie first so the macros survive an offline save
    const existing = await db.dailyNutrition.where('date').equals(data.date).first();
    const localRecord: LocalDailyNutrition = { ...data, updatedAt: now() };

    let localId: number;
    if (existing) {
      await db.dailyNutrition.update(existing.localId!, localRecord as UpdateSpec);
      localId = existing.localId!;
    } else {
      localId = await db.dailyNutrition.add(localRecord);
    }

    try {
      const server = await api.saveDailyNutrition(data);
      await db.dailyNutrition.update(localId, { serverId: server.id, userId: server.user_id });
      return server;
    } catch {
      await queueSync(
        'dailyNutrition',
        existing?.serverId ? 'update' : 'create',
        localId,
        existing?.serverId,
        data as unknown as Record<string, unknown>
      );
      return fromLocalNutrition({ ...localRecord, localId, serverId: existing?.serverId, userId: existing?.userId });
    }
  },

  async getNutritionHistory(
    startDate?: string,
    endDate?: string,
    userId?: number,
    limit?: number
  ): Promise<DailyNutrition[]> {
    if (userId) return api.getNutritionHistory(startDate, endDate, userId, limit);

    revalidate(`dailyNutrition:${startDate ?? ''}:${endDate ?? ''}:${limit ?? ''}`, async () => {
      const server = await api.getNutritionHistory(startDate, endDate, undefined, limit);
      return serializeMerge(() =>
        mergeServerRows('dailyNutrition', db.dailyNutrition, server, (n) => n.id, (n) => toLocalNutrition(n), true)
      );
    });

    // Serve from Dexie immediately
    let results: LocalDailyNutrition[];

    if (startDate && endDate) {
      results = await db.dailyNutrition.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.dailyNutrition.orderBy('date').reverse().toArray();
    }

    results = [...results].sort((a, b) => b.date.localeCompare(a.date));
    if (limit) results = results.slice(0, limit);
    return results.map(fromLocalNutrition);
  },

  // ── Photos (metadata caching, images cached by SW) ─────────────────────

  async getPhotos(
    startDate?: string,
    endDate?: string,
    view?: PhotoView,
    _userId?: number
  ): Promise<ProgressPhoto[]> {
    if (_userId) return api.getPhotos(startDate, endDate, view, _userId);

    revalidate(`photos:${startDate ?? ''}:${endDate ?? ''}:${view ?? ''}`, async () => {
      const serverPhotos = await api.getPhotos(startDate, endDate, view, undefined);
      return serializeMerge(() =>
        mergeServerRows('photos', db.photos, serverPhotos, (p) => p.id, (p) => toLocalPhoto(p))
      );
    });

    // Serve from Dexie immediately
    let results: LocalPhoto[];
    if (startDate && endDate) {
      results = await db.photos.where('date').between(startDate, endDate, true, true).toArray();
    } else {
      results = await db.photos.orderBy('date').toArray();
    }
    if (view) results = results.filter(p => p.view === view);
    return results.map(localToPhoto);
  },

  async getPhotosByDate(date: string, _userId?: number): Promise<ProgressPhoto[]> {
    if (_userId) return api.getPhotosByDate(date, _userId);

    revalidate(`photosByDate:${date}`, async () => {
      const serverPhotos = await api.getPhotosByDate(date, undefined);
      return serializeMerge(() =>
        mergeServerRows('photos', db.photos, serverPhotos, (p) => p.id, (p) => toLocalPhoto(p))
      );
    });

    const local = await db.photos.where('date').equals(date).toArray();
    return local.map(localToPhoto);
  },

  /**
   * Delete a photo and drop its cached metadata.
   *
   * Photo upload/delete are online-only (the UI blocks them offline), but the
   * local row has to go with it: a merge can only add and update rows, so a
   * server-side delete would otherwise stay visible in the cache until the
   * next `pullFromServer` pass.
   */
  async deletePhoto(id: number): Promise<void> {
    await api.deletePhoto(id);

    const existing = (await db.photos.where('serverId').equals(id).first())
      ?? await db.photos.get(id);
    if (existing) {
      await db.photos.delete(existing.localId!);
    }
  },

  /** Pull photo metadata for one date straight into the cache. Used right
   *  after an upload so the new photo appears without waiting for a bump. */
  async refreshPhotos(date: string): Promise<void> {
    const serverPhotos = await api.getPhotosByDate(date, undefined);
    await serializeMerge(() =>
      mergeServerRows('photos', db.photos, serverPhotos, (p) => p.id, (p) => toLocalPhoto(p))
    );
  },
};
