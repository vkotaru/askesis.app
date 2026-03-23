import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { api, type UserSettings, type ColorScheme } from '$lib/api/client';
import { db } from '$lib/db';

const DEFAULT_SETTINGS: UserSettings = {
  theme: 'system',
  font_size: 'medium',
  font_family: 'space-grotesk',
  content_width: 'medium',
  color_scheme: 'forest',
  distance_unit: 'km',
  measurement_unit: 'cm',
  weight_unit: 'kg',
  water_unit: 'ml',
  drive_parent_folder_id: null,
};

const FONT_MAP: Record<string, string> = {
  // Geometric
  'space-grotesk': "'Space Grotesk', system-ui, sans-serif",
  poppins: "'Poppins', system-ui, sans-serif",
  outfit: "'Outfit', system-ui, sans-serif",
  montserrat: "'Montserrat', system-ui, sans-serif",
  manrope: "'Manrope', system-ui, sans-serif",
  raleway: "'Raleway', system-ui, sans-serif",
  // Humanist
  inter: "'Inter', system-ui, sans-serif",
  'plus-jakarta': "'Plus Jakarta Sans', system-ui, sans-serif",
  'open-sans': "'Open Sans', system-ui, sans-serif",
  'source-sans': "'Source Sans 3', system-ui, sans-serif",
  'work-sans': "'Work Sans', system-ui, sans-serif",
  lato: "'Lato', system-ui, sans-serif",
  ubuntu: "'Ubuntu', system-ui, sans-serif",
  // Grotesque
  roboto: "'Roboto', system-ui, sans-serif",
  'dm-sans': "'DM Sans', system-ui, sans-serif",
  // Rounded
  nunito: "'Nunito', system-ui, sans-serif",
  rubik: "'Rubik', system-ui, sans-serif",
};

// Color schemes with primary and accent color palettes
const COLOR_SCHEMES: Record<ColorScheme, { primary: Record<string, string>; accent: Record<string, string> }> = {
  forest: {
    primary: {
      '50': '#f1f8f4', '100': '#dceee3', '200': '#bbddc9', '300': '#8ec5a7',
      '400': '#5ea883', '500': '#3d8b65', '600': '#2d7050', '700': '#265a42',
      '800': '#224836', '900': '#1d3c2e',
    },
    accent: {
      '50': '#fff5f3', '100': '#ffe8e3', '200': '#ffd5cc', '300': '#ffb5a6',
      '400': '#ff8a72', '500': '#f76a4d', '600': '#e44d2e', '700': '#c03d22',
      '800': '#9e3520', '900': '#833221',
    },
  },
  ocean: {
    primary: {
      '50': '#eff8ff', '100': '#dbeefe', '200': '#bfe3fe', '300': '#93d2fc',
      '400': '#60b8f9', '500': '#3b9af4', '600': '#257ce9', '700': '#1d65d6',
      '800': '#1e52ad', '900': '#1e4788',
    },
    accent: {
      '50': '#f0fdfa', '100': '#ccfbf1', '200': '#99f6e4', '300': '#5eead4',
      '400': '#2dd4bf', '500': '#14b8a6', '600': '#0d9488', '700': '#0f766e',
      '800': '#115e59', '900': '#134e4a',
    },
  },
  sunset: {
    primary: {
      '50': '#fff7ed', '100': '#ffedd5', '200': '#fed7aa', '300': '#fdba74',
      '400': '#fb923c', '500': '#f97316', '600': '#ea580c', '700': '#c2410c',
      '800': '#9a3412', '900': '#7c2d12',
    },
    accent: {
      '50': '#fdf2f8', '100': '#fce7f3', '200': '#fbcfe8', '300': '#f9a8d4',
      '400': '#f472b6', '500': '#ec4899', '600': '#db2777', '700': '#be185d',
      '800': '#9d174d', '900': '#831843',
    },
  },
  lavender: {
    primary: {
      '50': '#faf5ff', '100': '#f3e8ff', '200': '#e9d5ff', '300': '#d8b4fe',
      '400': '#c084fc', '500': '#a855f7', '600': '#9333ea', '700': '#7c3aed',
      '800': '#6b21a8', '900': '#581c87',
    },
    accent: {
      '50': '#fff1f2', '100': '#ffe4e6', '200': '#fecdd3', '300': '#fda4af',
      '400': '#fb7185', '500': '#f43f5e', '600': '#e11d48', '700': '#be123c',
      '800': '#9f1239', '900': '#881337',
    },
  },
  slate: {
    primary: {
      '50': '#f8fafc', '100': '#f1f5f9', '200': '#e2e8f0', '300': '#cbd5e1',
      '400': '#94a3b8', '500': '#64748b', '600': '#475569', '700': '#334155',
      '800': '#1e293b', '900': '#0f172a',
    },
    accent: {
      '50': '#eff6ff', '100': '#dbeafe', '200': '#bfdbfe', '300': '#93c5fd',
      '400': '#60a5fa', '500': '#3b82f6', '600': '#2563eb', '700': '#1d4ed8',
      '800': '#1e40af', '900': '#1e3a8a',
    },
  },
};

function createSettingsStore() {
  const { subscribe, set, update } = writable<UserSettings>(DEFAULT_SETTINGS);

  return {
    subscribe,
    set,

    async load() {
      try {
        // Try Dexie first for instant load
        const cached = await db.settings.get('userSettings');
        if (cached?.value) {
          const cachedSettings = cached.value as UserSettings;
          set(cachedSettings);
          applySettings(cachedSettings);
        }

        // Then fetch from server and update cache
        const settings = await api.getSettings();
        set(settings);
        applySettings(settings);
        await db.settings.put({ key: 'userSettings', value: settings });
      } catch (err) {
        // If server failed but we have cached settings, keep them
        const cached = await db.settings.get('userSettings').catch(() => null);
        if (cached?.value) {
          const cachedSettings = cached.value as UserSettings;
          set(cachedSettings);
          applySettings(cachedSettings);
        } else {
          console.error('Failed to load settings, using defaults:', err);
          set(DEFAULT_SETTINGS);
          applySettings(DEFAULT_SETTINGS);
        }
      }
    },

    async updateSetting<K extends keyof UserSettings>(key: K, value: UserSettings[K]) {
      // Optimistic update
      update((s) => {
        const newSettings = { ...s, [key]: value };
        applySettings(newSettings);
        return newSettings;
      });

      // Cache in Dexie
      const current = get({ subscribe });
      db.settings.put({ key: 'userSettings', value: current }).catch(() => {});

      // Persist to server
      try {
        await api.updateSettings({ [key]: value });
      } catch (err) {
        console.error('Failed to save settings:', err);
      }
    },
  };
}

function applySettings(settings: UserSettings) {
  if (!browser) return;

  const root = document.documentElement;

  // Theme
  if (
    settings.theme === 'dark' ||
    (settings.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  ) {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }

  // Font size - map presets to pixel values
  const fontSizeMap: Record<string, string> = {
    'xs': '12px',
    'sm': '14px',
    'medium': '16px',
    'lg': '18px',
    'xl': '20px',
    '2xl': '24px',
  };
  root.style.setProperty('--content-font-size', fontSizeMap[settings.font_size] || '16px');

  // Font family - set CSS variable so body inherits it
  root.style.setProperty('--font-sans', FONT_MAP[settings.font_family] || FONT_MAP['space-grotesk']);

  // Color scheme - set CSS variables for primary and accent colors
  const scheme = COLOR_SCHEMES[settings.color_scheme] || COLOR_SCHEMES.forest;
  for (const [shade, color] of Object.entries(scheme.primary)) {
    root.style.setProperty(`--color-primary-${shade}`, color);
  }
  for (const [shade, color] of Object.entries(scheme.accent)) {
    root.style.setProperty(`--color-accent-${shade}`, color);
  }
}

export const settings = createSettingsStore();

// Derived stores for convenience
export const contentWidth = derived(settings, ($s) => $s.content_width);
export const theme = derived(settings, ($s) => $s.theme);
