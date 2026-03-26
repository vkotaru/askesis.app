<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets, Coffee, FileText, Check, Utensils, ChevronLeft, ChevronRight, Heart, Upload, History, Calendar, CheckCircle } from 'lucide-svelte';
  import ImportModal from '$lib/components/ImportModal.svelte';
  import { clsx } from 'clsx';
  import { type DailyLog } from '$lib/api/client';
  import { offlineApi } from '$lib/stores/data';
  import { settings } from '$lib/stores/settings';
  import { formatWater, formatWeight, waterToMetric, waterFromMetric, weightToMetric, weightFromMetric, getWaterLabel, getWeightLabel } from '$lib/utils/units';

  let recentLogs: DailyLog[] = [];

  const FEELINGS = [
    { value: 'happy', emoji: '😊', label: 'Happy', color: 'bg-mood-5' },
    { value: 'energetic', emoji: '⚡', label: 'Energetic', color: 'bg-cardio-500' },
    { value: 'calm', emoji: '😌', label: 'Calm', color: 'bg-rest-500' },
    { value: 'focused', emoji: '🎯', label: 'Focused', color: 'bg-primary-500' },
    { value: 'grateful', emoji: '🙏', label: 'Grateful', color: 'bg-mood-4' },
    { value: 'motivated', emoji: '💪', label: 'Motivated', color: 'bg-strength-500' },
    { value: 'tired', emoji: '😴', label: 'Tired', color: 'bg-mood-2' },
    { value: 'stressed', emoji: '😰', label: 'Stressed', color: 'bg-mood-1' },
    { value: 'anxious', emoji: '😟', label: 'Anxious', color: 'bg-nutrition-600' },
    { value: 'sad', emoji: '😢', label: 'Sad', color: 'bg-mood-1' },
    { value: 'angry', emoji: '😤', label: 'Angry', color: 'bg-accent-500' },
    { value: 'sick', emoji: '🤒', label: 'Sick', color: 'bg-mood-2' },
    { value: 'sore', emoji: '🤕', label: 'Sore', color: 'bg-mood-3' },
    { value: 'meh', emoji: '😐', label: 'Meh', color: 'bg-gray-500' },
  ];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let saving = false;
  let saved = false;
  let showImportModal = false;

  // Track saved state per field for visual feedback
  let fieldSaved: Record<string, boolean> = {};

  // Form fields - directly bound (water stored in user's preferred unit)
  let weight: number | undefined;
  let sleep_hours: number | undefined;
  let steps: number | undefined;
  let water: number | undefined;
  let feelings: string[] = [];
  let caffeine_mg: number | undefined;
  let ate_outside = false;
  let notes = '';

  // Auto-save function - saves current form state
  async function autoSave(fieldName: string) {
    saving = true;
    try {
      await offlineApi.saveDailyLog({
        date: selectedDate,
        weight: weight ? weightToMetric(weight, $settings.weight_unit) : undefined,
        sleep_hours,
        steps,
        water_ml: water ? Math.round(waterToMetric(water, $settings.water_unit)) : undefined,
        feelings: feelings.length > 0 ? feelings : undefined,
        caffeine_mg,
        ate_outside,
        notes: notes || undefined,
      });
      // Show saved indicator for this field
      fieldSaved[fieldName] = true;
      fieldSaved = fieldSaved; // trigger reactivity
      setTimeout(() => {
        fieldSaved[fieldName] = false;
        fieldSaved = fieldSaved;
      }, 1500);
      loadRecentLogs();
    } catch (err) {
      console.error('Failed to auto-save:', err);
    } finally {
      saving = false;
    }
  }

  async function loadLog() {
    try {
      const log = await offlineApi.getDailyLog(selectedDate);
      weight = log.weight ? weightFromMetric(log.weight, $settings.weight_unit) : undefined;
      sleep_hours = log.sleep_hours;
      steps = log.steps;
      water = log.water_ml ? waterFromMetric(log.water_ml, $settings.water_unit) : undefined;
      feelings = log.feelings ?? [];
      caffeine_mg = log.caffeine_mg;
      ate_outside = log.ate_outside ?? false;
      notes = log.notes ?? '';
    } catch {
      // No log for this date, reset to defaults
      weight = undefined;
      sleep_hours = undefined;
      steps = undefined;
      water = undefined;
      feelings = [];
      caffeine_mg = undefined;
      ate_outside = false;
      notes = '';
    }
  }

  async function loadRecentLogs() {
    try {
      // Fetch 10 most recent logs (backend returns sorted by date desc)
      recentLogs = await offlineApi.getDailyLogs(undefined, undefined, undefined, 10);
    } catch (e) {
      console.error('Failed to load logs:', e);
      recentLogs = [];
    }
  }

  onMount(() => {
    loadLog();
    loadRecentLogs();
  });

  function goToDate(date: string) {
    selectedDate = date;
    loadLog();
  }

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadLog();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadLog();
  }

  function toggleFeeling(feeling: string) {
    if (feelings.includes(feeling)) {
      feelings = feelings.filter(f => f !== feeling);
    } else {
      feelings = [...feelings, feeling];
    }
    autoSave('feelings');
  }

  async function handleSubmit() {
    saving = true;
    saved = false;
    try {
      await offlineApi.saveDailyLog({
        date: selectedDate,
        weight: weight ? weightToMetric(weight, $settings.weight_unit) : undefined,
        sleep_hours,
        steps,
        water_ml: water ? Math.round(waterToMetric(water, $settings.water_unit)) : undefined,
        feelings: feelings.length > 0 ? feelings : undefined,
        caffeine_mg,
        ate_outside,
        notes: notes || undefined,
      });
      saved = true;
      loadRecentLogs(); // Refresh recent entries
      setTimeout(() => (saved = false), 2000);
    } catch (err) {
      console.error('Failed to save:', err);
    } finally {
      saving = false;
    }
  }

  function handleDateChange(e: Event) {
    selectedDate = (e.target as HTMLInputElement).value;
    loadLog();
  }

  // Check if current date has any data
  $: hasData = weight !== undefined || sleep_hours !== undefined || steps !== undefined ||
               water !== undefined || feelings.length > 0 || caffeine_mg !== undefined || notes !== '';

  // Check if selected date exists in recent logs
  $: dateHasEntry = recentLogs.some(log => log.date === selectedDate);
</script>

<svelte:head>
  <title>Daily Log - Askesis</title>
</svelte:head>

<div>
  <!-- Header -->
  <div class="mb-6">
    <h1 class="text-2xl font-bold">Daily Log</h1>
    <p class="text-gray-500 text-sm mt-1">Track your daily metrics</p>

    <!-- Date Navigation -->
    <div class="flex items-center justify-center gap-2 mt-4">
      <button
        type="button"
        on:click={prevDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronLeft size={20} />
      </button>
      <input
        type="date"
        value={selectedDate}
        on:change={handleDateChange}
        class={clsx(
          'input !w-auto max-w-[180px] text-center',
          hasData && 'border-primary-300 dark:border-primary-700'
        )}
      />
      <button
        type="button"
        on:click={nextDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronRight size={20} />
      </button>
    </div>

    <!-- Data status indicator -->
    {#if hasData}
      <div class="flex items-center justify-center gap-1 mt-2 text-sm text-primary-600 dark:text-primary-400">
        <CheckCircle size={14} />
        <span>Data recorded</span>
      </div>
    {/if}
  </div>

  <form on:submit|preventDefault={handleSubmit} class="card p-6">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div class="space-y-2">
        <label for="weight" class="label flex items-center gap-2">
          <Scale size={16} class="text-rest-500" />
          Weight <span class="text-gray-400 font-normal">({getWeightLabel($settings.weight_unit)})</span>
          {#if fieldSaved['weight']}
            <Check size={14} class="text-primary-500 animate-pulse" />
          {/if}
        </label>
        <input
          id="weight"
          type="number"
          step="any"
          bind:value={weight}
          on:blur={() => autoSave('weight')}
          placeholder="Enter weight"
          class={clsx('input', fieldSaved['weight'] && 'ring-2 ring-primary-300')}

        />
      </div>

      <div class="space-y-2">
        <label for="sleep" class="label flex items-center gap-2">
          <Moon size={16} class="text-strength-500" />
          Sleep <span class="text-gray-400 font-normal">(hours)</span>
          {#if fieldSaved['sleep']}
            <Check size={14} class="text-primary-500 animate-pulse" />
          {/if}
        </label>
        <input
          id="sleep"
          type="number"
          step="any"
          bind:value={sleep_hours}
          on:blur={() => autoSave('sleep')}
          placeholder="Enter sleep hours"
          class={clsx('input', fieldSaved['sleep'] && 'ring-2 ring-primary-300')}

        />
      </div>

      <div class="space-y-2">
        <label for="steps" class="label flex items-center gap-2">
          <Footprints size={16} class="text-cardio-500" />
          Steps
          {#if fieldSaved['steps']}
            <Check size={14} class="text-primary-500 animate-pulse" />
          {/if}
        </label>
        <input
          id="steps"
          type="number"
          bind:value={steps}
          on:blur={() => autoSave('steps')}
          placeholder="Enter steps"
          class={clsx('input', fieldSaved['steps'] && 'ring-2 ring-primary-300')}

        />
      </div>

      <div class="space-y-2">
        <label for="water" class="label flex items-center gap-2">
          <Droplets size={16} class="text-cardio-400" />
          Water <span class="text-gray-400 font-normal">({getWaterLabel($settings.water_unit)})</span>
          {#if fieldSaved['water']}
            <Check size={14} class="text-primary-500 animate-pulse" />
          {/if}
        </label>
        <input
          id="water"
          type="number"
          step="any"
          bind:value={water}
          on:blur={() => autoSave('water')}
          placeholder="Enter water intake"
          class={clsx('input', fieldSaved['water'] && 'ring-2 ring-primary-300')}

        />
      </div>

      <div class="space-y-2">
        <label for="caffeine" class="label flex items-center gap-2">
          <Coffee size={16} class="text-nutrition-600" />
          Caffeine <span class="text-gray-400 font-normal">(mg)</span>
          {#if fieldSaved['caffeine']}
            <Check size={14} class="text-primary-500 animate-pulse" />
          {/if}
        </label>
        <input
          id="caffeine"
          type="number"
          bind:value={caffeine_mg}
          on:blur={() => autoSave('caffeine')}
          placeholder="Enter caffeine"
          class={clsx('input', fieldSaved['caffeine'] && 'ring-2 ring-primary-300')}

        />
      </div>

      <div class="space-y-2">
        <span class="label flex items-center gap-2">
          <Utensils size={16} class="text-nutrition-500" />
          Ate Outside
          {#if fieldSaved['ate_outside']}
            <Check size={14} class="text-primary-500 animate-pulse" />
          {/if}
        </span>
        <button
          type="button"
          on:click={() => { ate_outside = !ate_outside; autoSave('ate_outside'); }}

          class={clsx(
            'relative inline-flex h-10 w-20 items-center rounded-full transition-colors',
            ate_outside
              ? 'bg-nutrition-500'
              : 'bg-gray-200 dark:bg-gray-600',
            fieldSaved['ate_outside'] && 'ring-2 ring-primary-300'
          )}
          role="switch"
          aria-checked={ate_outside}
        >
          <span
            class={clsx(
              'inline-block h-8 w-8 transform rounded-full bg-white shadow-md transition-transform',
              ate_outside ? 'translate-x-11' : 'translate-x-1'
            )}
          />
        </button>
      </div>
    </div>

    <!-- Feelings selector (multi-select) -->
    <div class="mt-8">
      <span class="label flex items-center gap-2">
        <Heart size={16} class="text-accent-500" />
        How are you feeling? <span class="text-gray-400 font-normal">(select all that apply)</span>
        {#if fieldSaved['feelings']}
          <Check size={14} class="text-primary-500 animate-pulse" />
        {/if}
      </span>
      <div class="flex gap-2 flex-wrap mt-2">
        {#each FEELINGS as { value, emoji, label, color }}
          <button
            type="button"
            on:click={() => toggleFeeling(value)}
            class={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-xl transition-all duration-200 text-sm',
              feelings.includes(value)
                ? `${color} text-white shadow-lg`
                : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
            )}
          >
            <span class="text-lg">{emoji}</span>
            <span class="font-medium">{label}</span>
          </button>
        {/each}
      </div>
    </div>

    <!-- Notes -->
    <div class="mt-6">
      <label for="notes" class="label flex items-center gap-2">
        <FileText size={16} class="text-gray-400" />
        Notes
        {#if fieldSaved['notes']}
          <Check size={14} class="text-primary-500 animate-pulse" />
        {/if}
      </label>
      <textarea
        id="notes"
        bind:value={notes}
        on:blur={() => autoSave('notes')}
        rows={3}
        placeholder="How was your day? Any observations..."
        class={clsx('input resize-none', fieldSaved['notes'] && 'ring-2 ring-primary-300')}
      ></textarea>
    </div>

    <!-- Auto-save indicator -->
    {#if saving}
      <div class="mt-4 text-sm text-gray-500 flex items-center gap-2 justify-end">
        <span class="animate-spin">⏳</span>
        Saving...
      </div>
    {/if}
  </form>

<!-- Import Button -->
    <div class="mt-6">
      <button
        on:click={() => (showImportModal = true)}
        class="btn-secondary w-full flex items-center justify-center gap-2"
      >
        <Upload size={20} />
        Import Bulk
      </button>
    </div>

<!-- Recent Entries -->
  {#if recentLogs.length > 0}
    <div class="card p-6 mt-6">
      <div class="flex items-center gap-2 mb-4">
        <History size={20} class="text-primary-500" />
        <h2 class="text-lg font-semibold">Recent Entries</h2>
        <span class="text-sm text-gray-400 ml-auto">{recentLogs.length} days</span>
      </div>

      <!-- Mobile: Card-based list -->
      <div class="md:hidden space-y-2">
        {#each recentLogs as log}
          <button
            type="button"
            on:click={() => goToDate(log.date)}
            class={clsx(
              'w-full p-3 rounded-xl text-left transition-all',
              log.date === selectedDate
                ? 'bg-primary-100 dark:bg-gray-700 border-2 border-primary-300 dark:border-primary-500'
                : 'bg-gray-50 dark:bg-gray-700/50 border-2 border-transparent hover:border-gray-200 dark:hover:border-gray-600'
            )}
          >
            <div class="flex items-center justify-between mb-2">
              <span class="font-semibold">{format(parseISO(log.date), 'MMM d, EEE')}</span>
              {#if log.feelings && log.feelings.length > 0}
                <div class="flex gap-0.5">
                  {#each log.feelings.slice(0, 3) as feeling}
                    {@const feelingData = FEELINGS.find(f => f.value === feeling)}
                    {#if feelingData}
                      <span class="text-sm">{feelingData.emoji}</span>
                    {/if}
                  {/each}
                </div>
              {/if}
            </div>
            <div class="flex flex-wrap gap-3 text-sm text-gray-600 dark:text-gray-400">
              {#if log.weight}
                <span class="flex items-center gap-1">
                  <Scale size={12} class="text-rest-500" />
                  {formatWeight(log.weight, $settings.weight_unit)}
                </span>
              {/if}
              {#if log.sleep_hours}
                <span class="flex items-center gap-1">
                  <Moon size={12} class="text-strength-500" />
                  {log.sleep_hours}h
                </span>
              {/if}
              {#if log.steps}
                <span class="flex items-center gap-1">
                  <Footprints size={12} class="text-cardio-500" />
                  {log.steps.toLocaleString()}
                </span>
              {/if}
              {#if log.water_ml}
                <span class="flex items-center gap-1">
                  <Droplets size={12} class="text-cardio-400" />
                  {formatWater(log.water_ml, $settings.water_unit)}
                </span>
              {/if}
              {#if log.caffeine_mg}
                <span class="flex items-center gap-1">
                  <Coffee size={12} class="text-nutrition-600" />
                  {log.caffeine_mg}mg
                </span>
              {/if}
              {#if log.ate_outside}
                <span class="flex items-center gap-1">
                  <Utensils size={12} class="text-nutrition-500" />
                  Ate out
                </span>
              {/if}
              {#if !log.weight && !log.sleep_hours && !log.steps && !log.water_ml && !log.caffeine_mg}
                <span class="text-gray-400 text-xs">No data recorded</span>
              {/if}
            </div>
            {#if log.notes}
              <div class="mt-2 text-xs text-gray-500 truncate flex items-center gap-1">
                <FileText size={12} class="text-gray-400" />
                {log.notes}
              </div>
            {/if}
          </button>
        {/each}
      </div>

      <!-- Desktop: Table view -->
      <div class="hidden md:block overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-gray-200 dark:border-gray-700">
              <th class="pb-3 font-medium text-gray-500">Date</th>
              <th class="pb-3 font-medium text-gray-500">Weight</th>
              <th class="pb-3 font-medium text-gray-500">Sleep</th>
              <th class="pb-3 font-medium text-gray-500">Steps</th>
              <th class="pb-3 font-medium text-gray-500">Water</th>
              <th class="pb-3 font-medium text-gray-500">Caffeine</th>
              <th class="pb-3 font-medium text-gray-500">Ate Out</th>
              <th class="pb-3 font-medium text-gray-500">Feelings</th>
              <th class="pb-3 font-medium text-gray-500">Notes</th>
            </tr>
          </thead>
          <tbody>
            {#each recentLogs as log}
              <tr
                class={clsx(
                  'border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors',
                  log.date === selectedDate && 'bg-primary-50 dark:bg-gray-700'
                )}
                on:click={() => goToDate(log.date)}
              >
                <td class="py-3">
                  <div class="flex items-center gap-2">
                    <Calendar size={14} class="text-gray-400" />
                    <span class="font-medium">{format(parseISO(log.date), 'MMM d')}</span>
                    <span class="text-gray-400 text-xs">{format(parseISO(log.date), 'EEE')}</span>
                  </div>
                </td>
                <td class="py-3">
                  {#if log.weight}
                    <span class="flex items-center gap-1">
                      <Scale size={14} class="text-rest-500" />
                      {formatWeight(log.weight, $settings.weight_unit)}
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.sleep_hours}
                    <span class="flex items-center gap-1">
                      <Moon size={14} class="text-strength-500" />
                      {log.sleep_hours} hrs
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.steps}
                    <span class="flex items-center gap-1">
                      <Footprints size={14} class="text-cardio-500" />
                      {log.steps.toLocaleString()}
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.water_ml}
                    <span class="flex items-center gap-1">
                      <Droplets size={14} class="text-cardio-400" />
                      {formatWater(log.water_ml, $settings.water_unit)}
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.caffeine_mg}
                    <span class="flex items-center gap-1">
                      <Coffee size={14} class="text-nutrition-600" />
                      {log.caffeine_mg}mg
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.ate_outside}
                    <span class="flex items-center gap-1">
                      <Utensils size={14} class="text-nutrition-500" />
                      Yes
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.feelings && log.feelings.length > 0}
                    <div class="flex gap-1 flex-wrap">
                      {#each log.feelings.slice(0, 3) as feeling}
                        {@const feelingData = FEELINGS.find(f => f.value === feeling)}
                        {#if feelingData}
                          <span class="text-base" title={feelingData.label}>{feelingData.emoji}</span>
                        {/if}
                      {/each}
                      {#if log.feelings.length > 3}
                        <span class="text-xs text-gray-400">+{log.feelings.length - 3}</span>
                      {/if}
                    </div>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if log.notes}
                    <span class="flex items-center gap-1" title={log.notes}>
                      <FileText size={14} class="text-gray-400" />
                      <span class="text-xs text-gray-500 truncate max-w-[100px]">{log.notes}</span>
                    </span>
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>

<ImportModal
  bind:show={showImportModal}
  dataType="daily-logs"
  title="Import Daily Logs"
  on:success={() => { loadLog(); loadRecentLogs(); }}
/>
