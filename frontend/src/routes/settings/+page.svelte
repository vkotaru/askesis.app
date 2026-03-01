<script lang="ts">
  import { Sun, Moon, Monitor, Type, Maximize2, Settings2 } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { settings } from '$lib/stores/settings';
  import type { UserSettings } from '$lib/api/client';

  type Theme = UserSettings['theme'];
  type FontSize = UserSettings['font_size'];
  type FontFamily = UserSettings['font_family'];
  type ContentWidth = UserSettings['content_width'];

  const FONT_SIZES: { value: FontSize; label: string; size: string }[] = [
    { value: 'small', label: 'Small', size: '14px' },
    { value: 'medium', label: 'Medium', size: '16px' },
    { value: 'large', label: 'Large', size: '18px' },
  ];

  const FONTS: { value: FontFamily; label: string; preview: string }[] = [
    { value: 'space-grotesk', label: 'Space Grotesk', preview: 'Modern geometric' },
    { value: 'inter', label: 'Inter', preview: 'Clean & readable' },
    { value: 'plus-jakarta', label: 'Plus Jakarta Sans', preview: 'Friendly & warm' },
    { value: 'dm-sans', label: 'DM Sans', preview: 'Geometric simplicity' },
    { value: 'outfit', label: 'Outfit', preview: 'Contemporary' },
    { value: 'nunito', label: 'Nunito', preview: 'Rounded & soft' },
    { value: 'rubik', label: 'Rubik', preview: 'Slightly rounded' },
  ];

  const CONTENT_WIDTHS: { value: ContentWidth; label: string; description: string }[] = [
    { value: 'narrow', label: 'Narrow', description: '768px - Focused reading' },
    { value: 'medium', label: 'Medium', description: '1024px - Balanced' },
    { value: 'wide', label: 'Wide', description: '1280px - More space' },
    { value: 'full', label: 'Full', description: '100% - Maximum width' },
  ];

  const themes: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: 'light', icon: Sun, label: 'Light' },
    { value: 'dark', icon: Moon, label: 'Dark' },
    { value: 'system', icon: Monitor, label: 'System' },
  ];
</script>

<svelte:head>
  <title>Settings - Askesis</title>
</svelte:head>

<div>
  <div class="mb-6">
    <h1 class="text-2xl font-bold">Settings</h1>
    <p class="text-gray-500 text-sm mt-1">Customize your experience</p>
  </div>

  <div class="space-y-6">
    <!-- Theme -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Sun size={20} class="text-nutrition-500" />
        <h2 class="text-lg font-semibold">Theme</h2>
      </div>
      <div class="flex flex-wrap gap-3">
        {#each themes as { value, icon: Icon, label }}
          <button
            on:click={() => settings.updateSetting('theme', value)}
            class={clsx(
              'flex items-center gap-2 px-4 py-3 rounded-xl border-2 transition-all',
              $settings.theme === value
                ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400'
                : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
            )}
          >
            <Icon size={18} />
            {label}
          </button>
        {/each}
      </div>
    </div>

    <!-- Typography -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Type size={20} class="text-cardio-500" />
        <h2 class="text-lg font-semibold">Typography</h2>
      </div>

      <!-- Font Family -->
      <div class="mb-6">
        <label class="label">Font Family</label>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {#each FONTS as { value, label, preview }}
            <button
              on:click={() => settings.updateSetting('font_family', value)}
              class={clsx(
                'text-left px-4 py-3 rounded-xl border-2 transition-all',
                $settings.font_family === value
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30'
                  : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
              )}
              style="font-family: '{label}', system-ui, sans-serif"
            >
              <span class="font-semibold block">{label}</span>
              <span class="text-sm text-gray-500">{preview}</span>
            </button>
          {/each}
        </div>
      </div>

      <!-- Font Size -->
      <div>
        <label class="label">Font Size</label>
        <div class="flex gap-3">
          {#each FONT_SIZES as option}
            <button
              on:click={() => settings.updateSetting('font_size', option.value)}
              class={clsx(
                'px-4 py-3 rounded-xl border-2 transition-all flex-1',
                $settings.font_size === option.value
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30'
                  : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
              )}
            >
              <span class="font-medium block">{option.label}</span>
              <span class="text-sm text-gray-500">{option.size}</span>
            </button>
          {/each}
        </div>
      </div>
    </div>

    <!-- Layout -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Maximize2 size={20} class="text-strength-500" />
        <h2 class="text-lg font-semibold">Layout</h2>
      </div>

      <div>
        <label class="label">Content Width</label>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {#each CONTENT_WIDTHS as { value, label, description }}
            <button
              on:click={() => settings.updateSetting('content_width', value)}
              class={clsx(
                'text-left px-4 py-3 rounded-xl border-2 transition-all',
                $settings.content_width === value
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30'
                  : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
              )}
            >
              <span class="font-medium block">{label}</span>
              <span class="text-xs text-gray-500">{description}</span>
            </button>
          {/each}
        </div>

        <!-- Preview bar -->
        <div class="mt-4 p-4 bg-gray-100 dark:bg-gray-700 rounded-xl">
          <p class="text-xs text-gray-500 mb-2">Preview</p>
          <div class="relative h-4 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
            <div
              class="absolute inset-y-0 left-1/2 -translate-x-1/2 bg-primary-400 rounded-full transition-all duration-300"
              style="width: {$settings.content_width === 'narrow' ? '40%' : $settings.content_width === 'medium' ? '60%' : $settings.content_width === 'wide' ? '80%' : '100%'}"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- About -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Settings2 size={20} class="text-rest-500" />
        <h2 class="text-lg font-semibold">About</h2>
      </div>
      <p class="text-gray-600 dark:text-gray-400">
        Askesis is a personal health tracking app for you and your family.
      </p>
      <div class="mt-4 flex items-center gap-4 text-sm text-gray-500">
        <span>Version 0.1.0</span>
        <span class="w-1 h-1 rounded-full bg-gray-300"></span>
        <span>Settings sync across devices</span>
      </div>
    </div>
  </div>
</div>
