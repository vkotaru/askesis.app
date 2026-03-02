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

export interface Activity {
  id: number;
  date: string;
  name: string;
  activity_type: 'cardio' | 'strength';
  duration_mins?: number;
  calories?: number;
  distance_km?: number;
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

export interface UserSettings {
  theme: 'light' | 'dark' | 'system';
  font_size: 'small' | 'medium' | 'large';
  font_family: string;
  content_width: 'narrow' | 'medium' | 'wide' | 'full';
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
  file_path: string;
  notes?: string;
  url: string;
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
  getDailyLogs: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    return fetchJSON<DailyLog[]>(`/api/daily-log/?${params}`);
  },
  getDailyLog: (date: string) => fetchJSON<DailyLog>(`/api/daily-log/${date}`),
  saveDailyLog: (data: DailyLogInput) =>
    fetchJSON<DailyLog>('/api/daily-log/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Nutrition
  getMeals: (date?: string) => {
    const params = date ? `?meal_date=${date}` : '';
    return fetchJSON<Meal[]>(`/api/nutrition/meals${params}`);
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
  getActivities: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    return fetchJSON<Activity[]>(`/api/activities/?${params}`);
  },
  createActivity: (data: ActivityInput) =>
    fetchJSON<Activity>('/api/activities/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteActivity: (id: number) =>
    fetchJSON(`/api/activities/${id}`, { method: 'DELETE' }),
  getCalendar: (year: number, month: number) =>
    fetchJSON<Record<string, CalendarEvent[]>>(
      `/api/activities/calendar/${year}/${month}`
    ),

  // Settings
  getSettings: () => fetchJSON<UserSettings>('/api/settings/'),
  updateSettings: (data: Partial<UserSettings>) =>
    fetchJSON<UserSettings>('/api/settings/', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Body Measurements
  getMeasurements: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    return fetchJSON<BodyMeasurement[]>(`/api/measurements/?${params}`);
  },
  getLatestMeasurement: () => fetchJSON<BodyMeasurement | null>('/api/measurements/latest'),
  getMeasurement: (date: string) => fetchJSON<BodyMeasurement>(`/api/measurements/${date}`),
  saveMeasurement: (data: BodyMeasurementInput) =>
    fetchJSON<BodyMeasurement>('/api/measurements/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteMeasurement: (id: number) =>
    fetchJSON(`/api/measurements/${id}`, { method: 'DELETE' }),

  // Progress Photos
  getPhotos: (startDate?: string, endDate?: string, view?: PhotoView) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (view) params.set('view', view);
    return fetchJSON<ProgressPhoto[]>(`/api/photos/?${params}`);
  },
  getPhotosByDate: (date: string) =>
    fetchJSON<ProgressPhoto[]>(`/api/photos/date/${date}`),
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
};
