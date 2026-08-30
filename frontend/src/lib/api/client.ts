// Types
export interface User {
  id: number;
  email: string;
  name: string;
  username?: string;
}

export interface LoginResponse {
  id: number;
  email: string;
  name: string;
  username: string;
}

export interface DailyLog {
  id: number;
  date: string;
  weight?: number;
  sleep_hours?: number;
  steps?: number;
  water_ml?: number;
  feelings?: string[];
  caffeine_mg?: number;
  ate_outside?: boolean;
  notes?: string;
  /**
   * Per-field provenance, e.g. `{ steps: 'garmin', weight: 'manual' }`.
   * Server-owned and read-only — it is stripped from anything pushed back, so
   * a client can never relabel an importer's value as the user's own. A field
   * missing from the map is unknown, which is every row predating the column.
   */
  sources?: Record<string, string>;
}

export interface DailyNutrition {
  id: number;
  user_id: number;
  date: string;
  protein_g?: number;
  carbs_g?: number;
  fat_g?: number;
  notes?: string;
}

export type DailyNutritionInput = Omit<DailyNutrition, 'id' | 'user_id'>;

export type DailyLogInput = Omit<DailyLog, 'id' | 'sources'>;

export interface FoodItem {
  id: number;
  user_id?: number;
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
}

export type FoodItemInput = Omit<FoodItem, 'id' | 'user_id' | 'source'>;

export interface ExternalFoodResult {
  external_id: string;
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
  source: string;
}

export interface MealFoodItem {
  id: number;
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
}

export interface MealFoodItemInput {
  food_item_id: number;
  quantity: number;
  notes?: string;
}

export interface Meal {
  id: number;
  date: string;
  label: string;
  time?: string;
  calories?: number;
  description?: string;
  photo_path?: string;
  ai_analysis?: string;
  photo_url?: string;
  food_items?: MealFoodItem[];
  computed_calories?: number;
  computed_protein_g?: number;
  computed_carbs_g?: number;
  computed_fat_g?: number;
}

export interface MealInput {
  date: string;
  label: string;
  time?: string;
  calories?: number;
  description?: string;
  food_items?: MealFoodItemInput[];
}

export interface FoodAnalysis {
  calories?: number;
  description?: string;
  foods: string[];
  macros?: {
    protein_g?: number;
    carbs_g?: number;
    fat_g?: number;
  };
}

export interface Exercise {
  id?: number;
  name: string;
  sets?: number;
  reps?: string;
  weight_kg?: number;
  notes?: string;
}

export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night';

export interface Activity {
  id: number;
  date: string;
  name: string;
  activity_type: 'cardio' | 'strength';
  time_of_day?: TimeOfDay;
  duration_mins?: number;
  calories?: number;
  distance_km?: number;
  url?: string;
  notes?: string;
  tags?: string;
  icon?: string;
  /** Importer that created this row; absent for anything hand-entered. Not the
   *  same claim as `url` pointing at garmin.com, which only means you pasted a
   *  link. Read-only. */
  source?: string;
  external_id?: string;
  exercises: Exercise[];
}

export type ActivityInput = Omit<Activity, 'id' | 'source' | 'external_id'>;

export interface GarminRun {
  started_at: string;
  finished_at: string | null;
  ok: boolean;
  running: boolean;
  trigger: string;
  summary: Record<string, number>;
  errors: string[];
}

export interface GarminStatus {
  enabled: boolean;
  configured: boolean;
  scheduled_hour: number | null;
  timezone: string;
  lookback_days: number;
  sync_username: string | null;
  is_owner: boolean;
  running: boolean;
  /** The token is gone or rejected — a person has to go and re-login. */
  needs_reauth: boolean;
  /** Garmin is rate-limiting. Deliberately distinct from needs_reauth: logging
   *  in again to "fix" a 429 is what turns a short block into a long one. */
  rate_limited: boolean;
  last_run: GarminRun | null;
}

export interface CalendarEvent {
  id: number;
  name: string;
  type: string;
  duration_mins?: number;
  icon?: string;
}

export interface RaceDistanceInfo {
  id: string;
  label: string;
  km: number;
  min_weeks: number;
  max_weeks: number;
}

export interface TrainingPlan {
  id: number;
  plan_name: string;
  plan_display_name: string;
  race_date: string;
  race_distance_km: number;
  start_date: string;
  status: 'active' | 'completed' | 'cancelled';
  created_at: string;
}

export interface TrainingPlanDetail extends TrainingPlan {
  planned_workouts: PlannedWorkout[];
}

export interface PlannedWorkout {
  id: number;
  plan_id: number;
  week_number: number;
  day_of_week: number;
  date: string;
  workout_type: string;
  description: string;
  target_distance_km?: number;
  target_pace_description?: string;
  completed: boolean;
  activity_id?: number;
  actual_distance_km?: number;
}

export interface WeeklyProgress {
  week_number: number;
  week_start: string;
  planned_distance_km: number;
  actual_distance_km: number;
  planned_run_km: number;
  actual_run_km: number;
  planned_bike_km: number;
  actual_bike_km: number;
  workouts_planned: number;
  workouts_completed: number;
}

export type ColorScheme = 'forest' | 'ocean' | 'sunset' | 'lavender' | 'slate';
export type DistanceUnit = 'km' | 'mi';
export type MeasurementUnit = 'cm' | 'in';
export type WeightUnit = 'kg' | 'lb';
export type WaterUnit = 'ml' | 'L' | 'oz' | 'cups';

export interface UserSettings {
  theme: 'light' | 'dark' | 'system';
  font_size: 'xs' | 'sm' | 'medium' | 'lg' | 'xl' | '2xl';
  font_family: string;
  content_width: 'narrow' | 'medium' | 'wide' | 'full';
  color_scheme: ColorScheme;
  distance_unit: DistanceUnit;
  measurement_unit: MeasurementUnit;
  weight_unit: WeightUnit;
  water_unit: WaterUnit;
  calorie_target?: number | null;
  protein_target?: number | null;
  /** Weekly training plan. Distances are km — convert only for display. */
  weekly_run_km?: number | null;
  weekly_bike_km?: number | null;
  /** Comma-separated discipline keys, e.g. "strength,stretch,swim". */
  weekly_disciplines?: string | null;
}

export interface BodyMeasurement {
  id: number;
  date: string;
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
}

export type BodyMeasurementInput = Omit<BodyMeasurement, 'id'>;

export type PhotoView = 'front' | 'side' | 'back';

export interface ProgressPhoto {
  id: number;
  date: string;
  view: PhotoView;
  notes?: string;
  url: string;
}

// Sharing types
export type DataCategory = 'daily_logs' | 'nutrition' | 'activities' | 'measurements' | 'photos';

export interface DataShare {
  id: number;
  shared_with_id: number;
  shared_with_name: string;
  shared_with_email: string;
  categories: DataCategory[];
}

export interface SharedWithMe {
  id: number;
  owner_id: number;
  owner_name: string;
  owner_email: string;
  categories: DataCategory[];
}

export interface ShareableUser {
  id: number;
  name: string;
  email: string;
}

// Import types
export interface ImportPreview {
  columns: string[];
  rows: Record<string, string>[];
  total_rows: number;
}

export interface ColumnMapping {
  csv_column: string;
  field: string;
  unit?: string;
}

export interface ImportRequest {
  data: Record<string, string>[];
  column_mapping: ColumnMapping[];
  unit_mapping: Record<string, string>;
}

export interface ImportResult {
  success_count: number;
  error_count: number;
  errors: string[];
}

// API Client
import { apiUrl } from '$lib/config';
import { tryRefreshToken } from '$lib/auth';

/**
 * An HTTP-level failure. Extends Error so every existing `err instanceof Error`
 * / `err.message` call site keeps working; `status` and `code` are additive, for
 * callers that need to branch on the machine-readable part of a body (e.g. the
 * 409 `password_not_set` that /auth/login returns for an unclaimed account).
 */
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

async function doFetch(url: string, options?: RequestInit): Promise<Response> {
  return fetch(apiUrl(url), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    credentials: 'include',
  });
}

/**
 * Fetch a response body as an attachment and hand it to the browser as a
 * download. Honours the server's Content-Disposition filename when present.
 */
async function downloadFile(url: string, options?: RequestInit): Promise<void> {
  let res = await doFetch(url, options);

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      res = await doFetch(url, options);
    }
  }

  if (!res.ok) {
    if (res.status === 401) throw new Error('Unauthorized');
    try {
      const errorData = await res.json();
      throw new Error(errorData.detail || `HTTP ${res.status}`);
    } catch (e) {
      if (e instanceof Error && e.message !== `HTTP ${res.status}`) throw e;
      throw new Error(`HTTP ${res.status}`);
    }
  }

  const filename =
    res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? 'download';
  const blobUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  let res = await doFetch(url, options);

  // One transparent refresh attempt on 401. /auth/refresh itself never
  // re-enters this branch (relative URL match) so we avoid an infinite loop.
  // /auth/login is excluded too: a 401 there means bad credentials, and
  // refreshing a stale cookie can't change that.
  if (res.status === 401 && !url.startsWith('/auth/refresh') && !url.startsWith('/auth/login')) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      res = await doFetch(url, options);
    }
  }

  if (!res.ok) {
    if (res.status === 401) {
      throw new ApiError('Unauthorized', 401);
    }
    // Try to get error detail from response body
    try {
      const errorData = await res.json();
      // FastAPI's 422 `detail` is an array of field errors, not a string —
      // never render it raw. Fall back to something a person can act on
      // rather than "HTTP 422".
      const detail =
        typeof errorData.detail === 'string'
          ? errorData.detail
          : res.status === 422
            ? 'That value is not valid. Please check and try again.'
            : null;
      throw new ApiError(detail || `HTTP ${res.status}`, res.status, errorData.code);
    } catch (e) {
      if (e instanceof Error && e.message !== `HTTP ${res.status}`) throw e;
      throw new ApiError(`HTTP ${res.status}`, res.status);
    }
  }

  return res.json();
}

async function fetchFormData<T>(url: string, formData: FormData): Promise<T> {
  const res = await fetch(apiUrl(url), {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('Unauthorized');
    }
    throw new Error(`HTTP ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Auth
  getMe: () => fetchJSON<User>('/auth/me'),
  // Username-or-email + password sign-in. Returns JSON (not a redirect) so the
  // SPA stays mounted; the session cookie rides back on the response.
  login: (username: string, password: string) =>
    fetchJSON<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  // Claim an account that predates password auth (password_hash IS NULL), and
  // sign in with the password just set. Returns the same shape as login(), so
  // the caller reuses the post-login bootstrap. Rejected — with a body that
  // does not say why — for any account that already has a password.
  setInitialPassword: (username: string, password: string) =>
    fetchJSON<LoginResponse>('/auth/set-initial-password', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  // Create an account. Requires the server's registration code, and 404s when
  // REGISTRATION_CODE is unset — signup is off unless the operator turns it on,
  // so the login screen only offers it after probing this.
  signup: (body: {
    registration_code: string;
    username: string;
    email: string;
    name: string;
    password: string;
  }) => fetchJSON<LoginResponse>('/auth/signup', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => fetchJSON<{ status: string }>('/auth/logout', { method: 'POST' }),
  changePassword: (currentPassword: string, newPassword: string) =>
    fetchJSON<{ status: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  // Daily Log
  getDailyLogs: (startDate?: string, endDate?: string, userId?: number, limit?: number) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (userId) params.set('user_id', userId.toString());
    if (limit) params.set('limit', limit.toString());
    return fetchJSON<DailyLog[]>(`/api/daily-log/?${params}`);
  },
  getDailyLog: (date: string, userId?: number) => {
    const params = userId ? `?user_id=${userId}` : '';
    return fetchJSON<DailyLog>(`/api/daily-log/${date}${params}`);
  },
  saveDailyLog: (data: DailyLogInput) =>
    fetchJSON<DailyLog>('/api/daily-log/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Nutrition - Daily totals
  getDailyNutrition: (date: string, userId?: number) => {
    const params = userId ? `?user_id=${userId}` : '';
    return fetchJSON<DailyNutrition>(`/api/nutrition/daily/${date}${params}`);
  },
  saveDailyNutrition: (data: DailyNutritionInput) =>
    fetchJSON<DailyNutrition>('/api/nutrition/daily', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Nutrition - Meals
  getMeals: (date?: string, userId?: number, startDate?: string, endDate?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (date) params.set('meal_date', date);
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (userId) params.set('user_id', userId.toString());
    if (limit) params.set('limit', limit.toString());
    const query = params.toString() ? `?${params}` : '';
    return fetchJSON<Meal[]>(`/api/nutrition/meals${query}`);
  },
  getNutritionHistory: (startDate?: string, endDate?: string, userId?: number, limit?: number) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (userId) params.set('user_id', userId.toString());
    if (limit) params.set('limit', limit.toString());
    const query = params.toString() ? `?${params}` : '';
    return fetchJSON<DailyNutrition[]>(`/api/nutrition/daily${query}`);
  },
  createMeal: (data: MealInput) =>
    fetchJSON<Meal>('/api/nutrition/meals', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateMeal: (id: number, data: MealInput) =>
    fetchJSON<Meal>(`/api/nutrition/meals/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteMeal: (id: number) =>
    fetchJSON(`/api/nutrition/meals/${id}`, { method: 'DELETE' }),
  copyMealsFromYesterday: (targetDate: string) =>
    fetchJSON(`/api/nutrition/meals/copy-yesterday?target_date=${targetDate}`, {
      method: 'POST',
    }),
  uploadMealPhoto: (mealId: number, file: File, analyze = true) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('analyze', analyze.toString());
    return fetchFormData<Meal & { analysis?: FoodAnalysis }>(`/api/nutrition/meals/${mealId}/photo`, formData);
  },
  analyzeFoodPhoto: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchFormData<FoodAnalysis>('/api/nutrition/analyze-photo', formData);
  },
  getMealPhotoUrl: (mealId: number) => `/api/nutrition/meals/${mealId}/photo`,

  // Food Items
  searchFoods: (q?: string, category?: string, userOnly = false, limit = 50) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (category) params.set('category', category);
    if (userOnly) params.set('user_only', 'true');
    if (limit) params.set('limit', limit.toString());
    const query = params.toString() ? `?${params}` : '';
    return fetchJSON<FoodItem[]>(`/api/nutrition/foods${query}`);
  },
  createFoodItem: (data: FoodItemInput) =>
    fetchJSON<FoodItem>('/api/nutrition/foods', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateFoodItem: (id: number, data: FoodItemInput) =>
    fetchJSON<FoodItem>(`/api/nutrition/foods/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteFoodItem: (id: number) =>
    fetchJSON(`/api/nutrition/foods/${id}`, { method: 'DELETE' }),
  searchExternalFoods: (q: string, limit = 15) => {
    const params = new URLSearchParams({ q, limit: limit.toString() });
    return fetchJSON<ExternalFoodResult[]>(`/api/nutrition/foods/search-external?${params}`);
  },
  importExternalFood: (data: ExternalFoodResult) =>
    fetchJSON<FoodItem>('/api/nutrition/foods/import-external', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Activities
  getActivities: (startDate?: string, endDate?: string, userId?: number, limit?: number) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (userId) params.set('user_id', userId.toString());
    if (limit) params.set('limit', limit.toString());
    return fetchJSON<Activity[]>(`/api/activities/?${params}`);
  },
  createActivity: (data: ActivityInput) =>
    fetchJSON<Activity>('/api/activities/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateActivity: (id: number, data: ActivityInput) =>
    fetchJSON<Activity>(`/api/activities/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteActivity: (id: number) =>
    fetchJSON(`/api/activities/${id}`, { method: 'DELETE' }),
  getCalendar: (year: number, month: number, userId?: number) => {
    const params = userId ? `?user_id=${userId}` : '';
    return fetchJSON<Record<string, CalendarEvent[]>>(
      `/api/activities/calendar/${year}/${month}${params}`
    );
  },

  // Settings
  getSettings: () => fetchJSON<UserSettings>('/api/settings/'),
  updateSettings: (data: Partial<UserSettings>) =>
    fetchJSON<UserSettings>('/api/settings/', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  // Streams a JSON backup of the signed-in user's OWN rows straight to the
  // browser as a download; there is no server-side copy to point at, so this
  // returns nothing. Not a whole-database dump — see backend settings.py.
  downloadBackup: () => downloadFile('/api/settings/backup', { method: 'POST' }),

  // Body Measurements
  getMeasurements: (startDate?: string, endDate?: string, userId?: number) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (userId) params.set('user_id', userId.toString());
    return fetchJSON<BodyMeasurement[]>(`/api/measurements/?${params}`);
  },
  getLatestMeasurement: (userId?: number) => {
    const params = userId ? `?user_id=${userId}` : '';
    return fetchJSON<BodyMeasurement | null>(`/api/measurements/latest${params}`);
  },
  getMeasurement: (date: string, userId?: number) => {
    const params = userId ? `?user_id=${userId}` : '';
    return fetchJSON<BodyMeasurement>(`/api/measurements/${date}${params}`);
  },
  saveMeasurement: (data: BodyMeasurementInput) =>
    fetchJSON<BodyMeasurement>('/api/measurements/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteMeasurement: (id: number) =>
    fetchJSON(`/api/measurements/${id}`, { method: 'DELETE' }),

  // Progress Photos
  getPhotos: (startDate?: string, endDate?: string, view?: PhotoView, userId?: number) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (view) params.set('view', view);
    if (userId) params.set('user_id', userId.toString());
    return fetchJSON<ProgressPhoto[]>(`/api/photos/?${params}`);
  },
  getPhotosByDate: (date: string, userId?: number) => {
    const params = userId ? `?user_id=${userId}` : '';
    return fetchJSON<ProgressPhoto[]>(`/api/photos/date/${date}${params}`);
  },
  uploadPhoto: (file: File, date: string, view: PhotoView, notes?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('photo_date', date);
    formData.append('view', view);
    if (notes) formData.append('notes', notes);
    return fetchFormData<ProgressPhoto>('/api/photos/upload', formData);
  },
  deletePhoto: (id: number) =>
    fetchJSON(`/api/photos/${id}`, { method: 'DELETE' }),
  getPhotoUrl: (id: number) => `/api/photos/file/${id}`,

  // Sharing
  getMyShares: () => fetchJSON<DataShare[]>('/api/sharing/my-shares'),
  getSharedWithMe: () => fetchJSON<SharedWithMe[]>('/api/sharing/shared-with-me'),
  getShareableUsers: () => fetchJSON<ShareableUser[]>('/api/sharing/users'),
  createShare: (email: string, categories: DataCategory[]) =>
    fetchJSON<DataShare>('/api/sharing/', {
      method: 'POST',
      body: JSON.stringify({ shared_with_email: email, categories }),
    }),
  updateShare: (id: number, categories: DataCategory[]) =>
    fetchJSON<DataShare>(`/api/sharing/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ categories }),
    }),
  deleteShare: (id: number) =>
    fetchJSON(`/api/sharing/${id}`, { method: 'DELETE' }),

  // Import
  previewCsv: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchFormData<ImportPreview>('/api/import/preview', formData);
  },
  importActivities: (data: ImportRequest) =>
    fetchJSON<ImportResult>('/api/import/activities', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  importDailyLogs: (data: ImportRequest) =>
    fetchJSON<ImportResult>('/api/import/daily-logs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  importMeasurements: (data: ImportRequest) =>
    fetchJSON<ImportResult>('/api/import/measurements', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  importMeals: (data: ImportRequest) =>
    fetchJSON<ImportResult>('/api/import/meals', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Training Plans
  getRaceDistances: () => fetchJSON<RaceDistanceInfo[]>('/api/training/distances'),
  getTrainingPlans: () => fetchJSON<TrainingPlan[]>('/api/training/plans'),
  getTrainingPlan: (id: number) => fetchJSON<TrainingPlanDetail>(`/api/training/plans/${id}`),
  createTrainingPlan: (opts: { race_distance: string; race_date: string; total_weeks?: number; start_date?: string; terrain?: string; include_bike?: boolean; bike_intensity?: number; rest_days?: number }) =>
    fetchJSON<TrainingPlan>('/api/training/plans', {
      method: 'POST',
      body: JSON.stringify(opts),
    }),
  deleteTrainingPlan: (id: number) =>
    fetchJSON(`/api/training/plans/${id}`, { method: 'DELETE' }),
  updatePlanStatus: (id: number, status: string) =>
    fetchJSON<TrainingPlan>(`/api/training/plans/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
  completeWorkout: (workoutId: number, activityId?: number) =>
    fetchJSON<PlannedWorkout>(`/api/training/workouts/${workoutId}/complete`, {
      method: 'PUT',
      body: JSON.stringify({ activity_id: activityId }),
    }),
  uncompleteWorkout: (workoutId: number) =>
    fetchJSON<PlannedWorkout>(`/api/training/workouts/${workoutId}/uncomplete`, { method: 'PUT' }),
  updateWorkout: (workoutId: number, data: { workout_type?: string; description?: string; target_distance_km?: number; target_pace_description?: string }) =>
    fetchJSON<PlannedWorkout>(`/api/training/workouts/${workoutId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  getTrainingProgress: (planId: number) =>
    fetchJSON<WeeklyProgress[]>(`/api/training/plans/${planId}/progress`),
  getTrainingCalendar: (year: number, month: number) =>
    fetchJSON<Record<string, PlannedWorkout[]>>(`/api/training/calendar/${year}/${month}`),

  // Integrations. Server operational state — always api.*, never offlineApi.*:
  // this must not enter Dexie, and offline it should read as unavailable rather
  // than as a stale "last synced" that was true an hour ago.
  getGarminStatus: () => fetchJSON<GarminStatus>('/api/integrations/garmin/status'),
  // 202 and returns immediately; the pull is a blocking chain of rate-limited
  // requests. Poll getGarminStatus() for the outcome — failures inside the run
  // cannot come back as a status code here.
  runGarminSync: () =>
    fetchJSON<{ started: boolean; reason?: string }>('/api/integrations/garmin/sync', {
      method: 'POST',
    }),
};
