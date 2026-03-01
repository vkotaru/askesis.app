import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { api, type UserSettings } from '$lib/api/client';

const DEFAULT_SETTINGS: UserSettings = {
  theme: 'system',
  font_size: 'medium',
  font_family: 'space-grotesk',
  content_width: 'medium',
};

const FONT_MAP: Record<string, string> = {
  'space-grotesk': "'Space Grotesk', system-ui, sans-serif",
  inter: "'Inter', system-ui, sans-serif",
  'plus-jakarta': "'Plus Jakarta Sans', system-ui, sans-serif",
  'dm-sans': "'DM Sans', system-ui, sans-serif",
  outfit: "'Outfit', system-ui, sans-serif",
  nunito: "'Nunito', system-ui, sans-serif",
  rubik: "'Rubik', system-ui, sans-serif",
};

function createSettingsStore() {
  const { subscribe, set, update } = writable<UserSettings>(DEFAULT_SETTINGS);

  return {
    subscribe,
    set,

    async load() {
      try {
        const settings = await api.getSettings();
        set(settings);
        applySettings(settings);
      } catch {
        // Use defaults if not authenticated
        set(DEFAULT_SETTINGS);
      }
    },

    async updateSetting<K extends keyof UserSettings>(key: K, value: UserSettings[K]) {
      // Optimistic update
      update((s) => {
        const newSettings = { ...s, [key]: value };
        applySettings(newSettings);
        return newSettings;
      });

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

  // Font size
  root.style.fontSize =
    settings.font_size === 'small' ? '14px' : settings.font_size === 'large' ? '18px' : '16px';

  // Font family
  root.style.fontFamily = FONT_MAP[settings.font_family] || FONT_MAP['space-grotesk'];
}

export const settings = createSettingsStore();

// Derived stores for convenience
export const contentWidth = derived(settings, ($s) => $s.content_width);
export const theme = derived(settings, ($s) => $s.theme);
