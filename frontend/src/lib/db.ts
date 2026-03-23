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
  drive_file_id?: string;
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
}

// ── Database class ───────────────────────────────────────────────────────────

class AskesisDB extends Dexie {
  dailyLogs!: Table<LocalDailyLog, number>;
  activities!: Table<LocalActivity, number>;
  meals!: Table<LocalMeal, number>;
  foods!: Table<LocalFood, number>;
  measurements!: Table<LocalMeasurement, number>;
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

    // ── Future versions go here ────────────────────────────────────────────
    // Example:
    // this.version(2).stores({
    //   dailyLogs: '++localId, serverId, date, userId, updatedAt, [userId+date]',
    //   // ... repeat ALL tables even if unchanged
    // }).upgrade(tx => {
    //   // migration logic
    // });
  }
}

export const db = new AskesisDB();
