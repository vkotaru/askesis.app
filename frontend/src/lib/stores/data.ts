/**
 * Offline-aware data access layer backed by Dexie.
 *
 * Provides the same method signatures as the existing api client but:
 * - Reads return Dexie data instantly (works offline)
 * - Writes go to Dexie first (instant UI update), then sync to server
 * - If server write succeeds, updates serverId in Dexie
 * - If server write fails (offline), queues in pendingSync
 *
 * Components can gradually migrate from `api.*` to `offlineApi.*` calls.
 * The return types match the existing API types so no component changes needed.
 */

import { db, type LocalDailyLog, type LocalActivity, type LocalMeal, type LocalMeasurement, type LocalPhoto } from '$lib/db';
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

// ── Hydrate: populate Dexie from server on first load ────────────────────────

async function hydrateTable<T>(
  tableName: string,
  fetcher: () => Promise<T[]>,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toLocal: (item: T) => any
): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const table = (db as any)[tableName];
  const localCount = await table.count();
  if (localCount > 0) return; // Already hydrated

  try {
    const serverData = await fetcher();
    await table.bulkAdd(serverData.map(toLocal));
  } catch {
    // Server unavailable — will hydrate when online
  }
}

export async function hydrateFromServer(userId?: number): Promise<void> {
  // Use max server limit (500) to get complete data for offline use
  await Promise.all([
    hydrateTable('dailyLogs', () => api.getDailyLogs(undefined, undefined, undefined, 500), (log) => toLocalDailyLog(log, userId)),
    hydrateTable('activities', () => api.getActivities(undefined, undefined, undefined, 500), (a) => toLocalActivity(a, userId)),
    hydrateTable('meals', () => api.getMeals(undefined, undefined, undefined, undefined, 500), (m) => toLocalMeal(m, userId)),
    hydrateTable('foods', () => api.searchFoods(undefined, undefined, false, 200), (f) => ({
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
    })),
    hydrateTable('measurements', () => api.getMeasurements(undefined, undefined, undefined), (m) => toLocalMeasurement(m, userId)),
    hydrateTable('photos', () => api.getPhotos(undefined, undefined, undefined, undefined), (p) => ({
      serverId: p.id,
      date: p.date,
      view: p.view,
      drive_file_id: p.drive_file_id,
      notes: p.notes,
      url: p.url,
      updatedAt: now(),
    })),
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
    // Try local first
    let collection = db.dailyLogs.orderBy('date').reverse();

    if (startDate && endDate) {
      collection = db.dailyLogs.where('date').between(startDate, endDate, true, true).reverse();
    }

    let results = await collection.toArray();
    if (limit) results = results.slice(0, limit);

    if (results.length > 0) {
      return results.map(fromLocalDailyLog);
    }

    // No local data — try server and cache
    try {
      const serverLogs = await api.getDailyLogs(startDate, endDate, _userId, limit);
      for (const log of serverLogs) {
        const existing = await db.dailyLogs.where('serverId').equals(log.id).first();
        if (!existing) {
          await db.dailyLogs.add(toLocalDailyLog(log) as LocalDailyLog);
        }
      }
      return serverLogs;
    } catch {
      return [];
    }
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
    let results: LocalActivity[];

    if (startDate && endDate) {
      results = await db.activities.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.activities.orderBy('date').reverse().toArray();
    }

    if (limit) results = results.slice(0, limit);

    if (results.length > 0) {
      return results.map(fromLocalActivity);
    }

    try {
      const serverActivities = await api.getActivities(startDate, endDate, _userId, limit);
      for (const a of serverActivities) {
        const existing = await db.activities.where('serverId').equals(a.id).first();
        if (!existing) {
          await db.activities.add(toLocalActivity(a) as LocalActivity);
        }
      }
      return serverActivities;
    } catch {
      return [];
    }
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
    let results: LocalMeal[];

    if (date) {
      results = await db.meals.where('date').equals(date).toArray();
    } else if (startDate && endDate) {
      results = await db.meals.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.meals.orderBy('date').reverse().toArray();
    }

    if (limit) results = results.slice(0, limit);

    if (results.length > 0) {
      return results.map(fromLocalMeal);
    }

    try {
      const serverMeals = await api.getMeals(date, _userId, startDate, endDate, limit);
      for (const m of serverMeals) {
        const existing = await db.meals.where('serverId').equals(m.id).first();
        if (!existing) {
          await db.meals.add(toLocalMeal(m) as LocalMeal);
        }
      }
      return serverMeals;
    } catch {
      return [];
    }
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
    let results: LocalMeasurement[];

    if (startDate && endDate) {
      results = await db.measurements.where('date').between(startDate, endDate, true, true).reverse().toArray();
    } else {
      results = await db.measurements.orderBy('date').reverse().toArray();
    }

    if (results.length > 0) {
      return results.map(fromLocalMeasurement);
    }

    try {
      const serverMeasurements = await api.getMeasurements(startDate, endDate, _userId);
      for (const m of serverMeasurements) {
        const existing = await db.measurements.where('serverId').equals(m.id).first();
        if (!existing) {
          await db.measurements.add(toLocalMeasurement(m) as LocalMeasurement);
        }
      }
      return serverMeasurements;
    } catch {
      return [];
    }
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

  // ── Nutrition (pass-through with offline fallback) ─────────────────────

  async getDailyNutrition(date: string, userId?: number): Promise<DailyNutrition> {
    try {
      return await api.getDailyNutrition(date, userId);
    } catch {
      // Return empty nutrition for offline
      return { id: 0, user_id: 0, date } as DailyNutrition;
    }
  },

  async saveDailyNutrition(data: DailyNutritionInput): Promise<DailyNutrition> {
    try {
      return await api.saveDailyNutrition(data);
    } catch {
      return { id: 0, user_id: 0, ...data } as DailyNutrition;
    }
  },

  async getNutritionHistory(
    startDate?: string,
    endDate?: string,
    userId?: number,
    limit?: number
  ): Promise<DailyNutrition[]> {
    try {
      return await api.getNutritionHistory(startDate, endDate, userId, limit);
    } catch {
      return [];
    }
  },

  // ── Photos (metadata caching, images cached by SW) ─────────────────────

  async getPhotos(
    startDate?: string,
    endDate?: string,
    view?: PhotoView,
    _userId?: number
  ): Promise<ProgressPhoto[]> {
    let results: LocalPhoto[];

    if (startDate && endDate) {
      results = await db.photos.where('date').between(startDate, endDate, true, true).toArray();
    } else {
      results = await db.photos.orderBy('date').toArray();
    }

    if (view) {
      results = results.filter(p => p.view === view);
    }

    if (results.length > 0) {
      return results.map(p => ({
        id: p.serverId ?? p.localId!,
        date: p.date,
        view: p.view,
        drive_file_id: p.drive_file_id,
        notes: p.notes,
        url: p.url || api.getPhotoUrl(p.serverId ?? p.localId!),
      }));
    }

    try {
      const serverPhotos = await api.getPhotos(startDate, endDate, view, _userId);
      for (const p of serverPhotos) {
        const existing = await db.photos.where('serverId').equals(p.id).first();
        if (!existing) {
          await db.photos.add({
            serverId: p.id,
            date: p.date,
            view: p.view,
            drive_file_id: p.drive_file_id,
            notes: p.notes,
            url: p.url,
            updatedAt: now(),
          });
        }
      }
      return serverPhotos;
    } catch {
      return [];
    }
  },

  async getPhotosByDate(date: string, _userId?: number): Promise<ProgressPhoto[]> {
    const local = await db.photos.where('date').equals(date).toArray();

    if (local.length > 0) {
      return local.map(p => ({
        id: p.serverId ?? p.localId!,
        date: p.date,
        view: p.view,
        drive_file_id: p.drive_file_id,
        notes: p.notes,
        url: p.url || api.getPhotoUrl(p.serverId ?? p.localId!),
      }));
    }

    try {
      const serverPhotos = await api.getPhotosByDate(date, _userId);
      for (const p of serverPhotos) {
        const existing = await db.photos.where('serverId').equals(p.id).first();
        if (!existing) {
          await db.photos.add({
            serverId: p.id,
            date: p.date,
            view: p.view,
            drive_file_id: p.drive_file_id,
            notes: p.notes,
            url: p.url,
            updatedAt: now(),
          });
        }
      }
      return serverPhotos;
    } catch {
      return [];
    }
  },
};
