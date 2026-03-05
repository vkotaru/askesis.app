<script lang="ts">
  import { onMount } from 'svelte';
  import { Sun, Moon, Monitor, Type, Maximize2, Settings2, Users, Share2, Trash2, Plus, Check, Palette, Ruler } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { settings } from '$lib/stores/settings';
  import { api, type UserSettings, type DataShare, type SharedWithMe, type ShareableUser, type DataCategory, type ColorScheme } from '$lib/api/client';

  // Sharing state
  let myShares: DataShare[] = [];
  let sharedWithMe: SharedWithMe[] = [];
  let shareableUsers: ShareableUser[] = [];
  let loadingShares = true;
  let showAddShare = false;
  let selectedUserEmail = '';
  let selectedCategories: DataCategory[] = [];

  const CATEGORIES: { value: DataCategory; label: string }[] = [
    { value: 'daily_logs', label: 'Daily Logs' },
    { value: 'nutrition', label: 'Nutrition' },
    { value: 'activities', label: 'Activities' },
    { value: 'measurements', label: 'Measurements' },
    { value: 'photos', label: 'Photos' },
  ];

  async function loadShares() {
    loadingShares = true;
    try {
      [myShares, sharedWithMe, shareableUsers] = await Promise.all([
        api.getMyShares(),
        api.getSharedWithMe(),
        api.getShareableUsers(),
      ]);
    } catch (err) {
      console.error('Failed to load shares:', err);
    } finally {
      loadingShares = false;
    }
  }

  async function createShare() {
    if (!selectedUserEmail || selectedCategories.length === 0) return;
    try {
      await api.createShare(selectedUserEmail, selectedCategories);
      showAddShare = false;
      selectedUserEmail = '';
      selectedCategories = [];
      loadShares();
    } catch (err) {
      console.error('Failed to create share:', err);
    }
  }

  async function deleteShare(id: number) {
    if (!confirm('Remove this share?')) return;
    try {
      await api.deleteShare(id);
      loadShares();
    } catch (err) {
      console.error('Failed to delete share:', err);
    }
  }

  function toggleCategory(cat: DataCategory) {
    if (selectedCategories.includes(cat)) {
      selectedCategories = selectedCategories.filter(c => c !== cat);
    } else {
      selectedCategories = [...selectedCategories, cat];
    }
  }

  onMount(loadShares);

  type Theme = UserSettings['theme'];
  type FontSize = UserSettings['font_size'];
  type FontFamily = UserSettings['font_family'];
  type ContentWidth = UserSettings['content_width'];

  const FONT_SIZES: { value: FontSize; label: string; size: string }[] = [
    { value: 'small', label: 'Small', size: '14px' },
    { value: 'medium', label: 'Medium', size: '16px' },
    { value: 'large', label: 'Large', size: '18px' },
  ];

  const FONTS: { value: FontFamily; label: string; family: string; category: string }[] = [
    // Sans-serif - Geometric
    { value: 'space-grotesk', label: 'Space Grotesk', family: 'Space Grotesk', category: 'Geometric' },
    { value: 'poppins', label: 'Poppins', family: 'Poppins', category: 'Geometric' },
    { value: 'outfit', label: 'Outfit', family: 'Outfit', category: 'Geometric' },
    { value: 'montserrat', label: 'Montserrat', family: 'Montserrat', category: 'Geometric' },
    { value: 'manrope', label: 'Manrope', family: 'Manrope', category: 'Geometric' },
    { value: 'raleway', label: 'Raleway', family: 'Raleway', category: 'Geometric' },
    // Sans-serif - Humanist
    { value: 'inter', label: 'Inter', family: 'Inter', category: 'Humanist' },
    { value: 'plus-jakarta', label: 'Plus Jakarta Sans', family: 'Plus Jakarta Sans', category: 'Humanist' },
    { value: 'open-sans', label: 'Open Sans', family: 'Open Sans', category: 'Humanist' },
    { value: 'source-sans', label: 'Source Sans 3', family: 'Source Sans 3', category: 'Humanist' },
    { value: 'work-sans', label: 'Work Sans', family: 'Work Sans', category: 'Humanist' },
    { value: 'lato', label: 'Lato', family: 'Lato', category: 'Humanist' },
    { value: 'ubuntu', label: 'Ubuntu', family: 'Ubuntu', category: 'Humanist' },
    // Sans-serif - Grotesque
    { value: 'roboto', label: 'Roboto', family: 'Roboto', category: 'Grotesque' },
    { value: 'dm-sans', label: 'DM Sans', family: 'DM Sans', category: 'Grotesque' },
    // Sans-serif - Rounded
    { value: 'nunito', label: 'Nunito', family: 'Nunito', category: 'Rounded' },
    { value: 'rubik', label: 'Rubik', family: 'Rubik', category: 'Rounded' },
  ];

  $: selectedFont = FONTS.find(f => f.value === $settings.font_family);

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

  const COLOR_SCHEMES: { value: ColorScheme; label: string; primary: string; accent: string }[] = [
    { value: 'forest', label: 'Forest', primary: '#3d8b65', accent: '#f76a4d' },
    { value: 'ocean', label: 'Ocean', primary: '#3b9af4', accent: '#14b8a6' },
    { value: 'sunset', label: 'Sunset', primary: '#f97316', accent: '#ec4899' },
    { value: 'lavender', label: 'Lavender', primary: '#a855f7', accent: '#f43f5e' },
    { value: 'slate', label: 'Slate', primary: '#64748b', accent: '#3b82f6' },
  ];

  const DISTANCE_UNITS: { value: DistanceUnit; label: string }[] = [
    { value: 'km', label: 'Kilometers (km)' },
    { value: 'mi', label: 'Miles (mi)' },
  ];

  const MEASUREMENT_UNITS: { value: MeasurementUnit; label: string }[] = [
    { value: 'cm', label: 'Centimeters (cm)' },
    { value: 'in', label: 'Inches (in)' },
  ];

  const WEIGHT_UNITS: { value: WeightUnit; label: string }[] = [
    { value: 'kg', label: 'Kilograms (kg)' },
    { value: 'lb', label: 'Pounds (lb)' },
  ];

  const WATER_UNITS: { value: WaterUnit; label: string }[] = [
    { value: 'ml', label: 'Milliliters (ml)' },
    { value: 'L', label: 'Liters (L)' },
    { value: 'oz', label: 'Fluid ounces (oz)' },
    { value: 'cups', label: 'Cups' },
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

    <!-- Color Scheme -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Palette size={20} class="text-accent-500" />
        <h2 class="text-lg font-semibold">Color Scheme</h2>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {#each COLOR_SCHEMES as { value, label, primary, accent }}
          <button
            on:click={() => settings.updateSetting('color_scheme', value)}
            class={clsx(
              'flex flex-col items-center gap-2 px-4 py-4 rounded-xl border-2 transition-all',
              $settings.color_scheme === value
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30'
                : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
            )}
          >
            <div class="flex gap-1">
              <div class="w-6 h-6 rounded-full" style="background-color: {primary}"></div>
              <div class="w-6 h-6 rounded-full" style="background-color: {accent}"></div>
            </div>
            <span class="font-medium text-sm">{label}</span>
          </button>
        {/each}
      </div>
    </div>

    <!-- Units -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Ruler size={20} class="text-rest-500" />
        <h2 class="text-lg font-semibold">Units</h2>
      </div>
      <p class="text-sm text-gray-500 mb-4">Data is stored in metric units and converted for display based on your preferences.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <label class="label">Distance (running)</label>
          <select
            class="input"
            value={$settings.distance_unit}
            on:change={(e) => settings.updateSetting('distance_unit', e.currentTarget.value)}
          >
            {#each DISTANCE_UNITS as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="label">Body Measurements</label>
          <select
            class="input"
            value={$settings.measurement_unit}
            on:change={(e) => settings.updateSetting('measurement_unit', e.currentTarget.value)}
          >
            {#each MEASUREMENT_UNITS as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="label">Body Weight</label>
          <select
            class="input"
            value={$settings.weight_unit}
            on:change={(e) => settings.updateSetting('weight_unit', e.currentTarget.value)}
          >
            {#each WEIGHT_UNITS as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="label">Water Intake</label>
          <select
            class="input"
            value={$settings.water_unit}
            on:change={(e) => settings.updateSetting('water_unit', e.currentTarget.value)}
          >
            {#each WATER_UNITS as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </select>
        </div>
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
        <label for="font-family" class="label">Font Family</label>
        <select
          id="font-family"
          class="input max-w-md"
          value={$settings.font_family}
          on:change={(e) => settings.updateSetting('font_family', e.currentTarget.value)}
        >
          <optgroup label="Geometric">
            {#each FONTS.filter(f => f.category === 'Geometric') as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </optgroup>
          <optgroup label="Humanist">
            {#each FONTS.filter(f => f.category === 'Humanist') as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </optgroup>
          <optgroup label="Grotesque">
            {#each FONTS.filter(f => f.category === 'Grotesque') as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </optgroup>
          <optgroup label="Rounded">
            {#each FONTS.filter(f => f.category === 'Rounded') as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </optgroup>
        </select>
        <!-- Font Preview -->
        {#if selectedFont}
          <div class="mt-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
            <p class="text-xs text-gray-500 mb-2">Preview</p>
            <p
              class="text-xl font-medium"
              style="font-family: '{selectedFont.family}', system-ui, sans-serif"
            >
              The quick brown fox jumps over the lazy dog.
            </p>
            <p
              class="text-sm text-gray-600 dark:text-gray-400 mt-2"
              style="font-family: '{selectedFont.family}', system-ui, sans-serif"
            >
              0123456789 • ABCDEFGHIJKLMNOPQRSTUVWXYZ • abcdefghijklmnopqrstuvwxyz
            </p>
          </div>
        {/if}
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

    <!-- Data Sharing -->
    <div class="card p-6">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2">
          <Share2 size={20} class="text-accent-500" />
          <h2 class="text-lg font-semibold">Data Sharing</h2>
        </div>
        {#if !showAddShare && !loadingShares}
          <button
            on:click={() => (showAddShare = true)}
            class="flex items-center gap-2 px-3 py-2 text-sm bg-primary-500 text-white rounded-lg hover:bg-primary-600"
          >
            <Plus size={16} />
            Share with someone
          </button>
        {/if}
      </div>

      {#if loadingShares}
        <div class="flex items-center justify-center py-8">
          <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
        </div>
      {:else}
        <!-- Add Share Form -->
        {#if showAddShare}
          <div class="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
            <h3 class="font-medium mb-3">Share your data with</h3>

            <div class="mb-4">
              <label class="label">Select user</label>
              <select bind:value={selectedUserEmail} class="input">
                <option value="">Choose a user...</option>
                {#each shareableUsers.filter(u => !myShares.some(s => s.shared_with_email === u.email)) as user}
                  <option value={user.email}>{user.name} ({user.email})</option>
                {/each}
              </select>
            </div>

            <div class="mb-4">
              <label class="label">Categories to share</label>
              <div class="flex flex-wrap gap-2">
                {#each CATEGORIES as { value, label }}
                  <button
                    on:click={() => toggleCategory(value)}
                    class={clsx(
                      'px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors',
                      selectedCategories.includes(value)
                        ? 'bg-primary-500 text-white'
                        : 'bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-500'
                    )}
                  >
                    {#if selectedCategories.includes(value)}
                      <Check size={14} />
                    {/if}
                    {label}
                  </button>
                {/each}
              </div>
            </div>

            <div class="flex gap-3">
              <button on:click={() => (showAddShare = false)} class="btn-secondary">
                Cancel
              </button>
              <button
                on:click={createShare}
                disabled={!selectedUserEmail || selectedCategories.length === 0}
                class="btn-primary"
              >
                Share
              </button>
            </div>
          </div>
        {/if}

        <!-- My Shares -->
        <div class="mb-6">
          <h3 class="text-sm font-medium text-gray-500 mb-3 flex items-center gap-2">
            <Users size={16} />
            People I'm sharing with
          </h3>
          {#if myShares.length === 0}
            <p class="text-gray-500 text-sm py-4 text-center">You haven't shared your data with anyone yet.</p>
          {:else}
            <div class="space-y-3">
              {#each myShares as share}
                <div class="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                  {#if share.shared_with_picture}
                    <img src={share.shared_with_picture} alt={share.shared_with_name} class="w-10 h-10 rounded-full" />
                  {:else}
                    <div class="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center">
                      <span class="text-gray-600 dark:text-gray-300 font-medium">
                        {share.shared_with_name?.charAt(0) || '?'}
                      </span>
                    </div>
                  {/if}
                  <div class="flex-1 min-w-0">
                    <p class="font-medium truncate">{share.shared_with_name}</p>
                    <p class="text-xs text-gray-500 truncate">{share.categories.join(', ')}</p>
                  </div>
                  <button
                    on:click={() => deleteShare(share.id)}
                    class="p-2 text-gray-400 hover:text-red-500"
                    title="Remove share"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Shared With Me -->
        <div>
          <h3 class="text-sm font-medium text-gray-500 mb-3 flex items-center gap-2">
            <Share2 size={16} />
            People sharing with me
          </h3>
          {#if sharedWithMe.length === 0}
            <p class="text-gray-500 text-sm py-4 text-center">No one is sharing their data with you yet.</p>
          {:else}
            <div class="space-y-3">
              {#each sharedWithMe as share}
                <div class="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                  {#if share.owner_picture}
                    <img src={share.owner_picture} alt={share.owner_name} class="w-10 h-10 rounded-full" />
                  {:else}
                    <div class="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center">
                      <span class="text-gray-600 dark:text-gray-300 font-medium">
                        {share.owner_name?.charAt(0) || '?'}
                      </span>
                    </div>
                  {/if}
                  <div class="flex-1 min-w-0">
                    <p class="font-medium truncate">{share.owner_name}</p>
                    <p class="text-xs text-gray-500 truncate">{share.categories.join(', ')}</p>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
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
        <span>Version 0.2.0</span>
        <span class="w-1 h-1 rounded-full bg-gray-300"></span>
        <span>Settings sync across devices</span>
      </div>
    </div>
  </div>
</div>
