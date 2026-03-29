<script lang="ts">
  import { onMount } from 'svelte';
  import { Sun, Moon, Monitor, Type, Maximize2, Settings2, Users, Share2, Trash2, Plus, Check, Palette, Ruler, Download, Database, Cloud, Upload, FileSpreadsheet, RefreshCw, Link, Copy, RotateCw, Flame } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { settings } from '$lib/stores/settings';
  import { api, type UserSettings, type DataShare, type SharedWithMe, type ShareableUser, type DataCategory, type ColorScheme, type DistanceUnit, type MeasurementUnit, type WeightUnit, type WaterUnit } from '$lib/api/client';

  // Report link state
  let reportToken = '';
  let reportUrl = '';
  let reportLoading = false;
  let reportCopied = false;

  async function loadReportToken() {
    try {
      const res = await fetch('/api/report/token', { method: 'POST', credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        reportToken = data.token;
        reportUrl = `${window.location.origin}${data.url}`;
      }
    } catch { /* ignore */ }
  }

  async function regenerateReportToken() {
    reportLoading = true;
    try {
      const res = await fetch('/api/report/token/regenerate', { method: 'POST', credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        reportToken = data.token;
        reportUrl = `${window.location.origin}${data.url}`;
      }
    } catch { /* ignore */ }
    finally { reportLoading = false; }
  }

  async function revokeReportToken() {
    if (!confirm('Revoke report link? Anyone with the old link will lose access.')) return;
    reportLoading = true;
    try {
      await fetch('/api/report/token', { method: 'DELETE', credentials: 'include' });
      reportToken = '';
      reportUrl = '';
    } catch { /* ignore */ }
    finally { reportLoading = false; }
  }

  function copyReportUrl() {
    navigator.clipboard.writeText(reportUrl);
    reportCopied = true;
    setTimeout(() => (reportCopied = false), 2000);
  }

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

  onMount(() => {
    loadShares();
    loadReportToken();
  });

  // Helper functions to handle select changes with proper typing
  function handleDistanceUnitChange(e: Event) {
    settings.updateSetting('distance_unit', (e.target as HTMLSelectElement).value as DistanceUnit);
  }
  function handleMeasurementUnitChange(e: Event) {
    settings.updateSetting('measurement_unit', (e.target as HTMLSelectElement).value as MeasurementUnit);
  }
  function handleWeightUnitChange(e: Event) {
    settings.updateSetting('weight_unit', (e.target as HTMLSelectElement).value as WeightUnit);
  }
  function handleWaterUnitChange(e: Event) {
    settings.updateSetting('water_unit', (e.target as HTMLSelectElement).value as WaterUnit);
  }
  function handleFontSizeChange(size: string) {
    settings.updateSetting('font_size', size as UserSettings['font_size']);
  }

  let exporting = false;
  let backingUp = false;
  let backupMessage = '';
  let disconnecting = false;
  let restoring = false;
  let restoreMessage = '';
  let restoreFile: FileList | null = null;

  // Google Sheets sync
  let syncing = false;
  let syncMessage = '';
  let sheetIdInput = '';

  // Initialize sheet ID from settings
  $: if ($settings.google_sheet_id && !sheetIdInput) {
    sheetIdInput = $settings.google_sheet_id;
  }

  function extractSheetId(input: string): string {
    // If it's a Google Sheets URL, extract the ID
    // Format: https://docs.google.com/spreadsheets/d/SHEET_ID/edit...
    const urlMatch = input.match(/\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/);
    if (urlMatch) {
      return urlMatch[1];
    }
    // Otherwise return as-is (assume it's already just the ID)
    return input.trim();
  }

  async function saveSheetId() {
    // Extract ID from URL if needed
    if (sheetIdInput) {
      const extractedId = extractSheetId(sheetIdInput);
      if (extractedId !== sheetIdInput) {
        sheetIdInput = extractedId;
      }
    }
    if (sheetIdInput !== $settings.google_sheet_id) {
      await settings.updateSetting('google_sheet_id', sheetIdInput || null);
    }
  }

  async function syncToGoogleSheet() {
    // Save sheet ID first if changed
    await saveSheetId();

    if (!sheetIdInput) {
      syncMessage = 'Please enter a Google Sheet ID first';
      return;
    }

    syncing = true;
    syncMessage = '';
    try {
      const result = await api.syncToGoogleSheet();
      if (result.success) {
        const shortId = result.sheet_id ? `...${result.sheet_id.slice(-8)}` : '';
        syncMessage = `✓ ${result.message} [Sheet: ${shortId}]`;
      } else {
        syncMessage = 'Sync failed';
      }
    } catch (err) {
      syncMessage = err instanceof Error ? err.message : 'Sync failed';
    } finally {
      syncing = false;
    }
  }

  async function backupToCloud() {
    backingUp = true;
    backupMessage = '';
    try {
      const result = await api.backupDatabase();
      backupMessage = result.message;
    } catch (err) {
      backupMessage = err instanceof Error ? err.message : 'Backup failed';
    } finally {
      backingUp = false;
    }
  }

  async function disconnectDrive() {
    if (!confirm('Disconnect Google Drive? You can reconnect by logging out and back in.')) return;
    disconnecting = true;
    try {
      await api.disconnectDrive();
      backupMessage = 'Google Drive disconnected.';
    } catch (err) {
      backupMessage = err instanceof Error ? err.message : 'Disconnect failed';
    } finally {
      disconnecting = false;
    }
  }

  async function restoreFromBackup() {
    if (!restoreFile || restoreFile.length === 0) return;

    const file = restoreFile[0];
    if (!file.name.endsWith('.json')) {
      restoreMessage = 'Please select a JSON backup file';
      return;
    }

    if (!confirm('This will restore data from the backup. Existing records with the same ID will be skipped. Continue?')) {
      return;
    }

    restoring = true;
    restoreMessage = '';
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/settings/restore', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Restore failed');
      }

      const result = await response.json();
      restoreMessage = `${result.message} Tables: ${result.tables_restored.join(', ')}`;
      restoreFile = null;
    } catch (err) {
      restoreMessage = err instanceof Error ? err.message : 'Restore failed';
    } finally {
      restoring = false;
    }
  }

  async function exportData() {
    exporting = true;
    try {
      const response = await fetch('/api/export/sqlite', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Export failed');

      const blob = await response.blob();
      const filename = response.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1]
        || `askesis-${new Date().toISOString().split('T')[0]}.db`;

      // Download the file
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      exporting = false;
    }
  }

  type Theme = UserSettings['theme'];
  type FontFamily = UserSettings['font_family'];
  type ContentWidth = UserSettings['content_width'];

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
                ? 'border-primary-500 bg-primary-50 dark:bg-gray-700 text-primary-700 dark:text-white'
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
                ? 'border-primary-500 bg-primary-50 dark:bg-gray-700 text-primary-700 dark:text-white'
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
            on:change={handleDistanceUnitChange}
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
            on:change={handleMeasurementUnitChange}
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
            on:change={handleWeightUnitChange}
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
            on:change={handleWaterUnitChange}
          >
            {#each WATER_UNITS as { value, label }}
              <option value={value}>{label}</option>
            {/each}
          </select>
        </div>
      </div>
    </div>

    <!-- Nutrition Goals -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Flame size={20} class="text-nutrition-500" />
        <h2 class="text-lg font-semibold">Nutrition Goals</h2>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-md">
        <div>
          <label for="calorie-target" class="label">Daily Calorie Target</label>
          <input
            id="calorie-target"
            type="number"
            class="input"
            min="0"
            step="50"
            placeholder="e.g. 2000"
            value={$settings.calorie_target || ''}
            on:blur={(e) => {
              const val = parseInt(e.currentTarget.value);
              settings.updateSetting('calorie_target', val > 0 ? val : null);
            }}
          />
        </div>
        <div>
          <label for="protein-target" class="label">Daily Protein Target (g)</label>
          <input
            id="protein-target"
            type="number"
            class="input"
            min="0"
            step="5"
            placeholder="e.g. 150"
            value={$settings.protein_target || ''}
            on:blur={(e) => {
              const val = parseInt(e.currentTarget.value);
              settings.updateSetting('protein_target', val > 0 ? val : null);
            }}
          />
        </div>
        <p class="text-xs text-gray-400 sm:col-span-2">Shown as target lines on the nutrition chart</p>
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
        <div class="grid grid-cols-3 lg:grid-cols-6 gap-2">
          {#each [
            { value: 'xs', label: 'XS', size: '12px' },
            { value: 'sm', label: 'S', size: '14px' },
            { value: 'medium', label: 'M', size: '16px' },
            { value: 'lg', label: 'L', size: '18px' },
            { value: 'xl', label: 'XL', size: '20px' },
            { value: '2xl', label: '2XL', size: '24px' },
          ] as option (option.value)}
            <button
              on:click={() => handleFontSizeChange(option.value)}
              class={clsx(
                'px-3 py-2 rounded-xl border-2 transition-all text-center',
                $settings.font_size === option.value
                  ? 'border-primary-500 bg-primary-50 dark:bg-gray-700 text-primary-700 dark:text-white'
                  : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
              )}
            >
              <span class="font-medium block">{option.label}</span>
              <span class="text-xs text-gray-500">{option.size}</span>
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
                  ? 'border-primary-500 bg-primary-50 dark:bg-gray-700 text-primary-700 dark:text-white'
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

    <!-- Shareable Report -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-3">
        <Link size={20} class="text-primary-500" />
        <h2 class="text-lg font-semibold">Shareable Report</h2>
      </div>
      <p class="text-sm text-gray-500 mb-4">
        Generate a public link to a read-only summary of your weight trend and weekly activities. No personal details are shown.
      </p>

      {#if reportUrl}
        <div class="flex items-center gap-2 mb-3">
          <input
            type="text"
            readonly
            value={reportUrl}
            class="input flex-1 text-sm bg-gray-50 dark:bg-gray-700/50"
            on:click={(e) => e.currentTarget.select()}
          />
          <button
            on:click={copyReportUrl}
            class="btn-secondary px-3 py-2 flex items-center gap-1"
            title="Copy link"
          >
            {#if reportCopied}
              <Check size={16} class="text-green-500" />
            {:else}
              <Copy size={16} />
            {/if}
          </button>
        </div>
        <div class="flex items-center gap-2">
          <button
            on:click={regenerateReportToken}
            disabled={reportLoading}
            class="text-xs text-gray-500 hover:text-primary-500 flex items-center gap-1 transition-colors"
          >
            <RotateCw size={12} />
            New link
          </button>
          <span class="text-gray-300 dark:text-gray-600">·</span>
          <button
            on:click={revokeReportToken}
            disabled={reportLoading}
            class="text-xs text-gray-500 hover:text-red-500 flex items-center gap-1 transition-colors"
          >
            <Trash2 size={12} />
            Revoke
          </button>
        </div>
      {:else}
        <button
          on:click={loadReportToken}
          disabled={reportLoading}
          class="btn-primary px-4 py-2 text-sm flex items-center gap-2"
        >
          <Link size={16} />
          Generate Report Link
        </button>
      {/if}
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

    <!-- Google Drive -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Cloud size={20} class="text-primary-500" />
        <h2 class="text-lg font-semibold">Google Drive</h2>
      </div>
      <p class="text-sm text-gray-500 mb-4">
        Progress photos and backups are stored in your Google Drive. By default, they go to folders at the root of your Drive.
      </p>
      <div class="max-w-md mb-6">
        <label for="drive-folder" class="label">Parent Folder ID (optional)</label>
        <input
          id="drive-folder"
          type="text"
          class="input"
          placeholder="Leave empty for Drive root"
          value={$settings.drive_parent_folder_id || ''}
          on:change={(e) => settings.updateSetting('drive_parent_folder_id', e.currentTarget.value || null)}
        />
        <p class="text-xs text-gray-500 mt-2">
          To store photos inside a specific folder, paste its ID here. You can find the folder ID in the URL when viewing the folder in Google Drive.
        </p>
      </div>

      <!-- Database Backup -->
      <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
        <h3 class="font-medium mb-2">Database Backup</h3>
        <p class="text-sm text-gray-500 mb-3">
          Backup your database to Google Drive. This will overwrite any existing backup.
        </p>
        <button
          on:click={backupToCloud}
          disabled={backingUp}
          class="btn-secondary flex items-center gap-2"
        >
          {#if backingUp}
            <span class="animate-spin">⏳</span>
            Backing up...
          {:else}
            <Cloud size={18} />
            Backup to Drive
          {/if}
        </button>
        {#if backupMessage}
          <p class={clsx(
            'text-sm mt-2',
            backupMessage.includes('success') ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
          )}>
            {backupMessage}
          </p>
        {/if}
      </div>

      <!-- Disconnect Drive -->
      <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
        <h3 class="font-medium mb-2">Disconnect Google Drive</h3>
        <p class="text-sm text-gray-500 mb-3">
          Revoke Drive access and remove the stored token. You can reconnect by logging out and back in.
        </p>
        <button
          on:click={disconnectDrive}
          disabled={disconnecting}
          class="btn-secondary text-red-600 dark:text-red-400 flex items-center gap-2"
        >
          {#if disconnecting}
            <span class="animate-spin">...</span>
            Disconnecting...
          {:else}
            Disconnect Drive
          {/if}
        </button>
      </div>

      <!-- Database Restore -->
      <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
        <h3 class="font-medium mb-2">Restore from Backup</h3>
        <p class="text-sm text-gray-500 mb-3">
          Restore data from a JSON backup file. Records with existing IDs will be skipped.
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".json"
            bind:files={restoreFile}
            class="text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-gray-100 dark:file:bg-gray-700 file:text-gray-700 dark:file:text-gray-300 hover:file:bg-gray-200 dark:hover:file:bg-gray-600"
          />
          <button
            on:click={restoreFromBackup}
            disabled={restoring || !restoreFile || restoreFile.length === 0}
            class="btn-secondary flex items-center gap-2"
          >
            {#if restoring}
              <span class="animate-spin">⏳</span>
              Restoring...
            {:else}
              <Upload size={18} />
              Restore
            {/if}
          </button>
        </div>
        {#if restoreMessage}
          <p class={clsx(
            'text-sm mt-2',
            restoreMessage.includes('completed') ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
          )}>
            {restoreMessage}
          </p>
        {/if}
      </div>
    </div>

    <!-- Google Sheets Sync -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <FileSpreadsheet size={20} class="text-green-600" />
        <h2 class="text-lg font-semibold">Google Sheets Sync</h2>
      </div>
      <p class="text-sm text-gray-500 mb-4">
        Sync your data to a Google Sheet. Creates tabs for Daily_Log, Activities, Measurements, and Photos.
      </p>

      <div class="max-w-md mb-4">
        <label for="sheet-id" class="label">Google Sheet ID</label>
        <input
          id="sheet-id"
          type="text"
          class="input"
          placeholder="e.g. 1BxiM... (from the sheet URL)"
          bind:value={sheetIdInput}
          on:blur={saveSheetId}
        />
        <p class="text-xs text-gray-500 mt-2">
          Find this in your Google Sheet URL: docs.google.com/spreadsheets/d/<strong>[SHEET_ID]</strong>/edit
        </p>
      </div>

      <!-- Auto-sync interval -->
      <div class="max-w-md mb-4">
        <label for="sync-interval" class="label">Auto-sync interval</label>
        <select
          id="sync-interval"
          class="input"
          value={$settings.gsheet_sync_interval_hours ?? 0}
          on:change={(e) => {
            const val = parseInt(e.currentTarget.value);
            settings.updateSetting('gsheet_sync_interval_hours', val || null);
          }}
        >
          <option value={0}>Disabled (manual only)</option>
          <option value={6}>Every 6 hours</option>
          <option value={12}>Every 12 hours</option>
          <option value={24}>Every 24 hours</option>
        </select>
        <p class="text-xs text-gray-500 mt-1">
          Automatically sync your data to Google Sheets in the background.
        </p>
      </div>

      <div class="flex items-center gap-4">
        <button
          on:click={syncToGoogleSheet}
          disabled={syncing || !sheetIdInput}
          class="btn-primary flex items-center gap-2"
        >
          {#if syncing}
            <RefreshCw size={18} class="animate-spin" />
            Syncing...
          {:else}
            <RefreshCw size={18} />
            Sync Now
          {/if}
        </button>

        {#if $settings.last_gsheet_sync}
          <span class="text-sm text-gray-500">
            Last sync: {new Date($settings.last_gsheet_sync).toLocaleString()}
          </span>
        {/if}
      </div>

      {#if syncMessage}
        <p class={clsx(
          'text-sm mt-3',
          syncMessage.includes('success') ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
        )}>
          {syncMessage}
        </p>
      {/if}
    </div>

    <!-- Data Export -->
    <div class="card p-6">
      <div class="flex items-center gap-2 mb-4">
        <Database size={20} class="text-cardio-500" />
        <h2 class="text-lg font-semibold">Data Export</h2>
      </div>
      <p class="text-gray-600 dark:text-gray-400 mb-4">
        Export all your data to a SQLite database file for backup or analysis.
      </p>
      <button
        on:click={exportData}
        disabled={exporting}
        class="btn-secondary flex items-center gap-2"
      >
        {#if exporting}
          <span class="animate-spin">⏳</span>
          Exporting...
        {:else}
          <Download size={18} />
          Export Data (.db)
        {/if}
      </button>
      <p class="text-xs text-gray-500 mt-3">
        Use with the <code class="bg-gray-100 dark:bg-gray-700 px-1 rounded">askesis</code> Python package for data analysis.
      </p>
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
