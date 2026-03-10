<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets, Coffee, FileText, Check, Utensils, ChevronLeft, ChevronRight, Heart, Upload, History, Calendar } from 'lucide-svelte';
  import ImportModal from '$lib/components/ImportModal.svelte';
  import { clsx } from 'clsx';
  import { api, type DailyLog } from '$lib/api/client';
  import { viewingUserId, isViewingOther } from '$lib/stores/viewContext';

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

  // Form fields - directly bound
  let weight: number | undefined;
  let sleep_hours: number | undefined;
  let steps: number | undefined;
  let water_ml: number | undefined;
  let feelings: string[] = [];
  let caffeine_mg: number | undefined;
  let ate_outside = false;
  let notes = '';

  async function loadLog() {
    try {
      const log = await api.getDailyLog(selectedDate, $viewingUserId ?? undefined);
      weight = log.weight;
      sleep_hours = log.sleep_hours;
      steps = log.steps;
      water_ml = log.water_ml;
      feelings = log.feelings ?? [];
      caffeine_mg = log.caffeine_mg;
      ate_outside = log.ate_outside ?? false;
      notes = log.notes ?? '';
    } catch {
      // No log for this date, reset to defaults
      weight = undefined;
      sleep_hours = undefined;
      steps = undefined;
      water_ml = undefined;
      feelings = [];
      caffeine_mg = undefined;
      ate_outside = false;
      notes = '';
    }
  }

  async function loadRecentLogs() {
    try {
      const endDate = format(new Date(), 'yyyy-MM-dd');
      const startDate = format(subDays(new Date(), 30), 'yyyy-MM-dd');
      const logs = await api.getDailyLogs(startDate, endDate, $viewingUserId ?? undefined);
      // Sort by date descending and take last 10
      recentLogs = logs.sort((a, b) => b.date.localeCompare(a.date)).slice(0, 10);
    } catch {
      recentLogs = [];
    }
  }

  onMount(() => {
    loadLog();
    loadRecentLogs();
  });

  // Reload when viewing user changes
  $: $viewingUserId, loadLog();
  $: $viewingUserId, loadRecentLogs();

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
  }

  async function handleSubmit() {
    saving = true;
    saved = false;
    try {
      await api.saveDailyLog({
        date: selectedDate,
        weight,
        sleep_hours,
        steps,
        water_ml,
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
        class="input max-w-[180px] text-center"
      />
      <button
        type="button"
        on:click={nextDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronRight size={20} />
      </button>
    </div>
  </div>

  <form on:submit|preventDefault={handleSubmit} class="card p-6">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div class="space-y-2">
        <label for="weight" class="label flex items-center gap-2">
          <Scale size={16} class="text-rest-500" />
          Weight <span class="text-gray-400 font-normal">(kg)</span>
        </label>
        <input
          id="weight"
          type="number"
          step="0.1"
          bind:value={weight}
          placeholder="Enter weight"
          class="input"
        />
      </div>

      <div class="space-y-2">
        <label for="sleep" class="label flex items-center gap-2">
          <Moon size={16} class="text-strength-500" />
          Sleep <span class="text-gray-400 font-normal">(hours)</span>
        </label>
        <input
          id="sleep"
          type="number"
          step="0.5"
          bind:value={sleep_hours}
          placeholder="Enter sleep hours"
          class="input"
        />
      </div>

      <div class="space-y-2">
        <label for="steps" class="label flex items-center gap-2">
          <Footprints size={16} class="text-cardio-500" />
          Steps
        </label>
        <input
          id="steps"
          type="number"
          bind:value={steps}
          placeholder="Enter steps"
          class="input"
        />
      </div>

      <div class="space-y-2">
        <label for="water" class="label flex items-center gap-2">
          <Droplets size={16} class="text-cardio-400" />
          Water <span class="text-gray-400 font-normal">(ml)</span>
        </label>
        <input
          id="water"
          type="number"
          step="100"
          bind:value={water_ml}
          placeholder="Enter water intake"
          class="input"
        />
      </div>

      <div class="space-y-2">
        <label for="caffeine" class="label flex items-center gap-2">
          <Coffee size={16} class="text-nutrition-600" />
          Caffeine <span class="text-gray-400 font-normal">(mg)</span>
        </label>
        <input
          id="caffeine"
          type="number"
          bind:value={caffeine_mg}
          placeholder="Enter caffeine"
          class="input"
        />
      </div>

      <div class="space-y-2">
        <span class="label flex items-center gap-2">
          <Utensils size={16} class="text-nutrition-500" />
          Ate Outside
        </span>
        <button
          type="button"
          on:click={() => (ate_outside = !ate_outside)}
          class={clsx(
            'relative inline-flex h-10 w-20 items-center rounded-full transition-colors',
            ate_outside
              ? 'bg-nutrition-500'
              : 'bg-gray-200 dark:bg-gray-600'
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
      </label>
      <textarea
        id="notes"
        bind:value={notes}
        rows={3}
        placeholder="How was your day? Any observations..."
        class="input resize-none"
      ></textarea>
    </div>

    {#if !$isViewingOther}
      <div class="mt-6 flex justify-end">
        <button
          type="submit"
          disabled={saving}
          class={clsx('btn-primary flex items-center gap-2', saved && 'bg-primary-600')}
        >
          {#if saving}
            <span class="animate-spin">⏳</span>
            Saving...
          {:else if saved}
            <Check size={18} />
            Saved!
          {:else}
            Save Log
          {/if}
        </button>
      </div>
    {/if}
  </form>

<!-- Import Button -->
  {#if !$isViewingOther}
    <div class="mt-6">
      <button
        on:click={() => (showImportModal = true)}
        class="btn-secondary w-full flex items-center justify-center gap-2"
      >
        <Upload size={20} />
        Import Bulk
      </button>
    </div>
  {/if}

<!-- Recent Entries -->
  {#if recentLogs.length > 0}
    <div class="card p-6 mt-6">
      <div class="flex items-center gap-2 mb-4">
        <History size={20} class="text-primary-500" />
        <h2 class="text-lg font-semibold">Recent Entries</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-gray-200 dark:border-gray-700">
              <th class="pb-3 font-medium text-gray-500">Date</th>
              <th class="pb-3 font-medium text-gray-500">Weight</th>
              <th class="pb-3 font-medium text-gray-500">Sleep</th>
              <th class="pb-3 font-medium text-gray-500">Steps</th>
              <th class="pb-3 font-medium text-gray-500">Water</th>
              <th class="pb-3 font-medium text-gray-500">Feelings</th>
            </tr>
          </thead>
          <tbody>
            {#each recentLogs as log}
              <tr
                class={clsx(
                  'border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors',
                  log.date === selectedDate && 'bg-primary-50 dark:bg-primary-900/20'
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
                      {log.weight} kg
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
                      {log.water_ml} ml
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
