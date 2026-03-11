// Types
export interface User {
  id: number;
  email: string;
  name: string;
  picture?: string;
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
  // Daily nutrition totals
  total_calories?: number;
  protein_g?: number;
  carbs_g?: number;
  fat_g?: number;
}

export type DailyLogInput = Omit<DailyLog, 'id'>;

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
}

export type MealInput = Omit<Meal, 'id' | 'photo_path' | 'ai_analysis' | 'photo_url'>;

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
  exercises: Exercise[];
}

export type ActivityInput = Omit<Activity, 'id'>;

export interface CalendarEvent {
  id: number;
  name: string;
  type: string;
  duration_mins?: number;
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
  drive_parent_folder_id?: string | null;
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
  file_path?: string;  // Legacy local path (deprecated)
  drive_file_id?: string;  // Google Drive file ID
  notes?: string;
  url: string;
}

export interface DriveStatus {
  configured: boolean;
  working: boolean;
  message: string;
}

// Sharing types
export type DataCategory = 'daily_logs' | 'nutrition' | 'activities' | 'measurements' | 'photos';

export interface DataShare {
  id: number;
  shared_with_id: number;
  shared_with_name: string;
  shared_with_email: string;
  shared_with_picture?: string;
  categories: DataCategory[];
}

export interface SharedWithMe {
  id: number;
  owner_id: number;
  owner_name: string;
  owner_email: string;
  owner_picture?: string;
  categories: DataCategory[];
}

export interface ShareableUser {
  id: number;
  name: string;
  email: string;
  picture?: string;
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
async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
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

async function fetchFormData<T>(url: string, formData: FormData): Promise<T> {
  const res = await fetch(url, {
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

  // Nutrition
  getMeals: (date?: string, userId?: number) => {
    const params = new URLSearchParams();
    if (date) params.set('meal_date', date);
    if (userId) params.set('user_id', userId.toString());
    const query = params.toString() ? `?${params}` : '';
    return fetchJSON<Meal[]>(`/api/nutrition/meals${query}`);
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
  getDriveStatus: () => fetchJSON<DriveStatus>('/api/photos/drive-status'),

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
};
