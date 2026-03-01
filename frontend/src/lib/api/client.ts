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
}

export type MealInput = Omit<Meal, 'id'>;

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
};
