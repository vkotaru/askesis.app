<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets, Coffee, FileText, Check, Utensils, ChevronLeft, ChevronRight, Heart, Upload, History, Calendar, CheckCircle } from 'lucide-svelte';
  import ImportModal from '$lib/components/ImportModal.svelte';
  import SourceBadge from '$lib/components/SourceBadge.svelte';
  import { clsx } from 'clsx';
  import { api, type DailyLog } from '$lib/api/client';
  import { offlineApi, dataVersion } from '$lib/stores/data';
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

  // Which values came from a device rather than from you. Server-owned; this
  // page only ever reads it. The UI names for these fields aren't the column
  // names, so keep the translation in one place.
  let sources: Record<string, string> = {};
  const COLUMN_FOR: Record<string, string> = {
    weight: 'weight',
    sleep: 'sleep_hours',
    steps: 'steps',
    water: 'water_ml',
    caffeine: 'caffeine_mg',
    notes: 'notes',
  };

  // Form fields - directly bound (water stored in user's preferred unit)
  let weight: number | undefined;
  let sleep_hours: number | undefined;
  let steps: number | undefined;
  let water: number | undefined;
  let feelings: string[] = [];
  let caffeine_mg: number | undefined;
  let ate_outside = false;
  let notes = '';

  // ── Quick entry: the two things that still have to be typed by hand ──────
  //
  // Steps, sleep and activities arrive from Garmin. Weight does not (the scale
  // app does not sync), and neither do calories (they are read off MyFitnessPal
  // and copied over). So those are the daily task, and this page is built
  // around them.
  //
  // Meals here carry a label and a number and no food items, which is a
  // perfectly valid Meal row — the nutrition tab and the dashboard both just
  // sum `calories`, so nothing downstream has to know these were typed rather
  // than itemised.
  const QUICK_MEALS = ['Breakfast', 'Lunch', 'Dinner', 'Snack'] as const;

  let mealCals: Record<string, number | undefined> = {};
  // The row each label maps to, so an edit updates rather than piles up.
  let mealRowId: Record<string, number | undefined> = {};
  // A label the nutrition tab has split across several rows. Editing one of
  // them here would silently disagree with the total, so those go read-only
  // instead of guessing which row the number belongs to.
  let mealLocked: Record<string, boolean> = {};

  let protein_g: number | undefined;
  let carbs_g: number | undefined;
  let fat_g: number | undefined;

  $: totalCals = QUICK_MEALS.reduce((sum, l) => sum + (mealCals[l] ?? 0), 0);

  async function loadQuickEntry() {
    try {
      let meals = await offlineApi.getMeals(selectedDate, undefined);
      if (meals.length === 0) {
        // The offline layer answers from Dexie and refreshes in the background,
        // so a device that has not cached THIS date yet gets an empty array and
        // the real rows land later. For a chart that is fine; for a form it is
        // not — you would be looking at blank calorie boxes for a day you
        // already filled in, and typing into them would create duplicates.
        //
        // So when the cache has nothing, ask the server directly. Wrapped
        // because offline this must stay empty rather than throw, and it only
        // costs a request on days that genuinely have no meals logged.
        try {
          meals = await api.getMeals(selectedDate, undefined);
        } catch {
          // offline, or the server is unreachable — keep the empty result
        }
      }
      const byLabel: Record<string, typeof meals> = {};
      for (const m of meals) (byLabel[m.label] ??= []).push(m);

      for (const label of QUICK_MEALS) {
        const rows = byLabel[label] ?? [];
        mealCals[label] = rows.length ? rows.reduce((s, m) => s + (m.calories ?? 0), 0) : undefined;
        mealRowId[label] = rows.length === 1 ? rows[0].id : undefined;
        mealLocked[label] = rows.length > 1;
      }
      mealCals = mealCals; mealRowId = mealRowId; mealLocked = mealLocked;
    } catch {
      for (const label of QUICK_MEALS) {
        mealCals[label] = undefined; mealRowId[label] = undefined; mealLocked[label] = false;
      }
      mealCals = mealCals; mealRowId = mealRowId; mealLocked = mealLocked;
    }

    try {
      const n = await offlineApi.getDailyNutrition(selectedDate, undefined);
      protein_g = n?.protein_g ?? undefined;
      carbs_g = n?.carbs_g ?? undefined;
      fat_g = n?.fat_g ?? undefined;
    } catch {
      protein_g = undefined; carbs_g = undefined; fat_g = undefined;
    }
  }

  async function saveMeal(label: string) {
    if (mealLocked[label]) return;
    const value = mealCals[label];
    try {
      if (mealRowId[label] !== undefined) {
        await offlineApi.updateMeal(mealRowId[label]!, {
          date: selectedDate,
          label,
          calories: value ?? 0,
        });
      } else if (value !== undefined && value !== null) {
        // Only a real number creates a row. Tabbing through an empty field
        // should not litter the day with zero-calorie meals.
        const created = await offlineApi.createMeal({
          date: selectedDate,
          label,
          calories: value,
        });
        mealRowId[label] = created.id;
        mealRowId = mealRowId;
      }
      flashSaved(`meal:${label}`);
    } catch (err) {
      console.error('Failed to save meal calories:', err);
    }
  }

  async function saveMacros(field: string) {
    try {
      await offlineApi.saveDailyNutrition({
        date: selectedDate,
        protein_g,
        carbs_g,
        fat_g,
      });
      flashSaved(field);
    } catch (err) {
      console.error('Failed to save macros:', err);
    }
  }

  function flashSaved(key: string) {
    fieldSaved[key] = true;
    fieldSaved = fieldSaved;
    setTimeout(() => { fieldSaved[key] = false; fieldSaved = fieldSaved; }, 1500);
  }

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
      // You just typed over it, so it is yours now — the server records the
      // same thing. Reflect it here instead of leaving a stale watch icon
      // beside a number the watch no longer owns.
      const column = COLUMN_FOR[fieldName];
      if (column && sources[column]) {
        sources = { ...sources, [column]: 'manual' };
      }
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
      sources = log.sources ?? {};
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
      sources = {};
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

  // The page shows two independent records for one date — the daily log, and
  // the meals/macros behind the quick-entry card — so every date change has to
  // move both. One function, so a new navigation path cannot reload half a day.
  function loadDay() {
    loadLog();
    loadQuickEntry();
  }

  onMount(() => {
    loadDay();
    loadRecentLogs();
  });

  // Re-read the cache when a background revalidation actually changed
  // something. Only the list — reloading loadLog() would clobber whatever the
  // user is typing into the form.
  let seenDataVersion = $dataVersion;
  $: if ($dataVersion !== seenDataVersion) {
    seenDataVersion = $dataVersion;
    loadRecentLogs();
    refreshQuickEntry();
  }

  // The quick-entry card DOES follow background refreshes, unlike the form
  // below it, and it has to: reads are served from the local cache first, so on
  // a device that has not synced this date yet the first render is empty and
  // the real numbers arrive moments later. Without this they never appear until
  // the page is opened a second time.
  //
  // The clobbering risk that keeps loadLog() out of this block is handled by
  // refusing to refresh while the user is inside the card — a half-typed
  // calorie count must never be replaced mid-keystroke.
  let quickCard: HTMLElement | undefined;
  function refreshQuickEntry() {
    if (quickCard && quickCard.contains(document.activeElement)) return;
    loadQuickEntry();
  }

  function goToDate(date: string) {
    selectedDate = date;
    loadDay();
  }

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadDay();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadDay();
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
    loadDay();
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

  <!-- Quick entry — the only two things still typed by hand every day.
       Garmin supplies steps, sleep and activities; the scale app and the food
       tracker do not sync, so weight and calories land here. Everything else
       this page can record is real but occasional, and sits under "More". -->
  <div class="card p-6 space-y-5" bind:this={quickCard}>
    <div class="space-y-2">
      <label for="weight" class="label flex items-center gap-2">
        <Scale size={16} class="text-rest-500" />
        Weight <span class="text-gray-400 font-normal">({getWeightLabel($settings.weight_unit)})</span>
        <SourceBadge source={sources['weight']} />
        {#if fieldSaved['weight']}
          <Check size={14} class="text-primary-500 animate-pulse" />
        {/if}
      </label>
      <input
        id="weight"
        type="number"
        step="any"
        inputmode="decimal"
        bind:value={weight}
        on:blur={() => autoSave('weight')}
        placeholder="Enter weight"
        class={clsx('input text-lg', fieldSaved['weight'] && 'ring-2 ring-primary-300')}
      />
    </div>

    <div class="border-t border-gray-200 dark:border-gray-700 pt-5 space-y-3">
      <div class="flex items-baseline gap-2">
        <Utensils size={16} class="text-nutrition-500" />
        <span class="label mb-0">Calories</span>
        <span class="ml-auto text-sm text-gray-400">
          total
          <span class="ml-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-white"
            >{totalCals.toLocaleString()}</span
          >
        </span>
      </div>

      <div class="grid grid-cols-2 gap-3">
        {#each QUICK_MEALS as label}
          <div class="space-y-1">
            <label for="meal-{label}" class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
              {label}
              {#if fieldSaved[`meal:${label}`]}
                <Check size={12} class="text-primary-500 animate-pulse" />
              {/if}
            </label>
            <input
              id="meal-{label}"
              type="number"
              inputmode="numeric"
              bind:value={mealCals[label]}
              on:blur={() => saveMeal(label)}
              disabled={mealLocked[label]}
              placeholder="—"
              class={clsx(
                'input tabular-nums',
                mealLocked[label] && 'opacity-60 cursor-not-allowed',
                fieldSaved[`meal:${label}`] && 'ring-2 ring-primary-300'
              )}
            />
            {#if mealLocked[label]}
              <!-- Several rows share this label, so which one a typed number
                   belongs to is genuinely ambiguous. Showing the sum and
                   sending the user to the itemised view beats picking one. -->
              <p class="text-[10px] text-gray-400 leading-tight">
                itemised — edit in <a href="/nutrition" class="underline">Nutrition</a>
              </p>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <div class="border-t border-gray-200 dark:border-gray-700 pt-5 space-y-3">
      <span class="label mb-0">Macros <span class="text-gray-400 font-normal">(g)</span></span>
      <div class="grid grid-cols-3 gap-3">
        <div class="space-y-1">
          <label for="protein" class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
            Protein
            {#if fieldSaved['protein']}<Check size={12} class="text-primary-500 animate-pulse" />{/if}
          </label>
          <input id="protein" type="number" step="any" inputmode="decimal"
            bind:value={protein_g} on:blur={() => saveMacros('protein')} placeholder="—"
            class={clsx('input tabular-nums', fieldSaved['protein'] && 'ring-2 ring-primary-300')} />
        </div>
        <div class="space-y-1">
          <label for="carbs" class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
            Carbs
            {#if fieldSaved['carbs']}<Check size={12} class="text-primary-500 animate-pulse" />{/if}
          </label>
          <input id="carbs" type="number" step="any" inputmode="decimal"
            bind:value={carbs_g} on:blur={() => saveMacros('carbs')} placeholder="—"
            class={clsx('input tabular-nums', fieldSaved['carbs'] && 'ring-2 ring-primary-300')} />
        </div>
        <div class="space-y-1">
          <label for="fat" class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
            Fat
            {#if fieldSaved['fat']}<Check size={12} class="text-primary-500 animate-pulse" />{/if}
          </label>
          <input id="fat" type="number" step="any" inputmode="decimal"
            bind:value={fat_g} on:blur={() => saveMacros('fat')} placeholder="—"
            class={clsx('input tabular-nums', fieldSaved['fat'] && 'ring-2 ring-primary-300')} />
        </div>
      </div>
    </div>
  </div>

  <!-- Everything else this page records. Real, but not a daily task — sleep and
       steps arrive from Garmin, and water is not being counted. Collapsed so the
       two fields above are the whole screen on a phone. -->
  <details class="mt-6 group">
    <summary class="cursor-pointer select-none text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 flex items-center gap-2 py-2">
      <ChevronRight size={16} class="transition-transform group-open:rotate-90" />
      More — sleep, steps, water, caffeine, feelings, notes
    </summary>

  <form on:submit|preventDefault={handleSubmit} class="card p-6">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div class="space-y-2">
        <label for="sleep" class="label flex items-center gap-2">
          <Moon size={16} class="text-strength-500" />
          Sleep <span class="text-gray-400 font-normal">(hours)</span>
          <SourceBadge source={sources['sleep_hours']} />
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
          <SourceBadge source={sources['steps']} />
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
          <SourceBadge source={sources['water_ml']} />
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

  </details>

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
                  <SourceBadge source={log.sources?.steps} size={10} />
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
                      <SourceBadge source={log.sources?.steps} />
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
  on:success={() => { loadDay(); loadRecentLogs(); }}
/>
