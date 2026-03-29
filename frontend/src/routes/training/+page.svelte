<script lang="ts">
  import { onMount } from 'svelte';
  import { format, parseISO, differenceInDays, startOfWeek, endOfWeek, isWithinInterval } from 'date-fns';
  import { Target, Calendar, CheckCircle, Circle, Trophy, ChevronDown, Bike, PersonStanding } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type TrainingPlan, type RaceDistanceInfo, type TrainingPlanDetail, type PlannedWorkout, type WeeklyProgress } from '$lib/api/client';
  import { settings } from '$lib/stores/settings';
  import { distanceFromMetric, getDistanceLabel } from '$lib/utils/units';

  let loading = true;
  let plans: TrainingPlan[] = [];
  let activePlan: TrainingPlanDetail | null = null;
  let distances: RaceDistanceInfo[] = [];
  let progress: WeeklyProgress[] = [];

  // Create plan form
  let selectedDistance: string = 'marathon';
  let raceDate: string = '';
  type StartMode = 'auto' | 'weeks' | 'date';
  const START_MODE_OPTIONS: [StartMode, string][] = [['auto', 'Auto'], ['weeks', '# Weeks'], ['date', 'Start Date']];
  let startMode: StartMode = 'auto';
  let totalWeeks: number = 16;
  let startDate: string = '';
  let selectedTerrain: string = 'road';
  let includeBike: boolean = true;
  let bikeIntensity: number = 50;
  let restDays: number = 2;
  let creating = false;
  let errorMessage = '';

  const today = new Date();
  const todayStr = format(today, 'yyyy-MM-dd');

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const [plansData, distData] = await Promise.all([
        api.getTrainingPlans(),
        api.getRaceDistances(),
      ]);
      plans = plansData;
      distances = distData;

      const active = plans.find(p => p.status === 'active');
      if (active) {
        const [detail, prog] = await Promise.all([
          api.getTrainingPlan(active.id),
          api.getTrainingProgress(active.id),
        ]);
        activePlan = detail;
        progress = prog;
      }
    } catch (err) {
      console.error('Failed to load training data:', err);
    } finally {
      loading = false;
    }
  }

  async function createPlan() {
    if (!selectedDistance || !raceDate) return;
    creating = true;
    errorMessage = '';
    try {
      await api.createTrainingPlan({
        race_distance: selectedDistance,
        race_date: raceDate,
        ...(startMode === 'weeks' ? { total_weeks: totalWeeks } : {}),
        ...(startMode === 'date' ? { start_date: startDate } : {}),
        terrain: selectedTerrain,
        include_bike: includeBike,
        bike_intensity: bikeIntensity,
        rest_days: restDays,
      });
      await loadData();
      raceDate = '';
    } catch (err) {
      errorMessage = err instanceof Error ? err.message : 'Failed to create plan';
    } finally {
      creating = false;
    }
  }

  async function cancelPlan() {
    if (!activePlan || !confirm('Cancel this training plan?')) return;
    try {
      await api.updatePlanStatus(activePlan.id, 'cancelled');
      activePlan = null;
      progress = [];
      await loadData();
    } catch (err) {
      console.error('Failed to cancel plan:', err);
    }
  }

  async function toggleWorkout(pw: PlannedWorkout) {
    try {
      if (pw.completed) {
        await api.uncompleteWorkout(pw.id);
      } else {
        await api.completeWorkout(pw.id);
      }
      // Reload plan
      if (activePlan) {
        const [detail, prog] = await Promise.all([
          api.getTrainingPlan(activePlan.id),
          api.getTrainingProgress(activePlan.id),
        ]);
        activePlan = detail;
        progress = prog;
      }
    } catch (err) {
      console.error('Failed to toggle workout:', err);
    }
  }

  // Derived data
  $: daysToRace = activePlan ? differenceInDays(parseISO(activePlan.race_date), today) : 0;

  $: currentWeek = (() => {
    if (!activePlan) return 0;
    const start = parseISO(activePlan.start_date);
    const daysSinceStart = differenceInDays(today, start);
    return Math.max(1, Math.min(Math.floor(daysSinceStart / 7) + 1, activePlan.planned_workouts.length > 0 ? Math.max(...activePlan.planned_workouts.map(w => w.week_number)) : 1));
  })();

  $: totalWeeks = activePlan ? Math.max(...activePlan.planned_workouts.map(w => w.week_number), 0) : 0;

  $: thisWeekWorkouts = (() => {
    if (!activePlan) return [];
    const weekStart = startOfWeek(today, { weekStartsOn: 1 });
    const weekEnd = endOfWeek(today, { weekStartsOn: 1 });
    return activePlan.planned_workouts.filter(pw => {
      const d = parseISO(pw.date);
      return isWithinInterval(d, { start: weekStart, end: weekEnd });
    });
  })();

  // Progress chart — separate run and bike
  $: maxRunKm = Math.max(...progress.map(w => Math.max(w.planned_run_km, w.actual_run_km)), 1);
  $: maxBikeKm = Math.max(...progress.map(w => Math.max(w.planned_bike_km, w.actual_bike_km)), 1);
  $: hasBikeData = progress.some(w => w.planned_bike_km > 0 || w.actual_bike_km > 0);

  const WORKOUT_COLORS: Record<string, string> = {
    road_run: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    trail_run: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    treadmill_run: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-300',
    run: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    long_run: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
    tempo: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
    bike: 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
    cross_train: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    rest: 'bg-gray-100 text-gray-500 dark:bg-gray-700/50 dark:text-gray-400',
    race: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  };

  function distFmt(km: number | undefined | null): string {
    if (!km) return '';
    return `${distanceFromMetric(km, $settings.distance_unit).toFixed(1)} ${getDistanceLabel($settings.distance_unit)}`;
  }

  // Expanded week tracking
  let expandedWeek: number | null = null;
  let editingWorkout: number | null = null;
  let editDesc = '';
  let editDist = '';
  let editType = '';
  let editPace = '';

  function toggleWeekExpand(week: number) {
    expandedWeek = expandedWeek === week ? null : week;
    editingWorkout = null;
  }

  function startEdit(pw: PlannedWorkout) {
    editingWorkout = pw.id;
    editDesc = pw.description;
    editDist = pw.target_distance_km ? distanceFromMetric(pw.target_distance_km, $settings.distance_unit).toFixed(1) : '';
    editType = pw.workout_type;
    editPace = pw.target_pace_description || '';
  }

  async function saveEdit(pw: PlannedWorkout) {
    const distVal = editDist ? parseFloat(editDist) : 0;
    // Convert back to km if user uses miles
    const distKm = $settings.distance_unit === 'mi' ? distVal * 1.60934 : distVal;
    try {
      await api.updateWorkout(pw.id, {
        workout_type: editType,
        description: editDesc,
        target_distance_km: distKm,
        target_pace_description: editPace,
      });
      editingWorkout = null;
      if (activePlan) {
        activePlan = await api.getTrainingPlan(activePlan.id);
      }
    } catch (err) {
      console.error('Failed to update workout:', err);
    }
  }

  const WORKOUT_TYPES = ['road_run', 'trail_run', 'treadmill_run', 'long_run', 'bike', 'cross_train', 'rest', 'race'];
</script>

<svelte:head>
  <title>Training Plan - Askesis</title>
</svelte:head>

<div>
  <div class="mb-6">
    <h1 class="text-2xl font-bold flex items-center gap-2">
      <Target size={24} class="text-cardio-500" />
      Training Plan
    </h1>
    <p class="text-gray-500 text-sm mt-1">Plan and track your marathon training</p>
  </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else if activePlan}
    <!-- Active Plan View -->

    <!-- Race Countdown -->
    <div class="card p-6 mb-6">
      <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold">{activePlan.plan_display_name}</h2>
          <p class="text-sm text-gray-500">
            Race: {format(parseISO(activePlan.race_date), 'EEEE, MMMM d, yyyy')}
          </p>
        </div>
        <div class="text-right">
          <div class="text-3xl font-bold {daysToRace > 0 ? 'text-primary-500' : 'text-green-500'}">
            {daysToRace > 0 ? daysToRace : 0}
          </div>
          <div class="text-xs text-gray-400">days to race</div>
        </div>
      </div>

      <!-- Progress bar -->
      <div class="mt-4">
        <div class="flex justify-between text-xs text-gray-500 mb-1">
          <span>Week {currentWeek} of {totalWeeks}</span>
          <span>{Math.round((currentWeek / totalWeeks) * 100)}%</span>
        </div>
        <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            class="bg-primary-500 rounded-full h-2 transition-all"
            style="width: {Math.min((currentWeek / totalWeeks) * 100, 100)}%"
          ></div>
        </div>
      </div>

      <button on:click={cancelPlan} class="text-xs text-red-500 hover:text-red-700 mt-3">
        Cancel Plan
      </button>
    </div>

    <!-- This Week -->
    <div class="card p-6 mb-6">
      <h2 class="text-sm font-semibold text-gray-500 mb-4">This Week</h2>
      <div class="space-y-2">
        {#each thisWeekWorkouts as pw}
          {@const isToday = pw.date === todayStr}
          {@const isPast = pw.date < todayStr}
          <button
            on:click={() => toggleWorkout(pw)}
            class={clsx(
              'w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors',
              isToday ? 'ring-2 ring-primary-300 dark:ring-primary-700' : '',
              pw.completed ? 'opacity-70' : ''
            )}
          >
            {#if pw.completed}
              <CheckCircle size={20} class="text-green-500 flex-shrink-0" />
            {:else}
              <Circle size={20} class="text-gray-300 flex-shrink-0" />
            {/if}
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class={clsx('text-xs px-2 py-0.5 rounded-full', WORKOUT_COLORS[pw.workout_type] || WORKOUT_COLORS.run)}>
                  {pw.workout_type.replace('_', ' ')}
                </span>
                <span class={clsx('text-sm font-medium', pw.completed ? 'line-through text-gray-400' : '')}>
                  {pw.description}
                </span>
              </div>
              <div class="text-xs text-gray-400 mt-0.5">
                {format(parseISO(pw.date), 'EEE, MMM d')}
                {#if pw.target_distance_km}
                  &middot; {distFmt(pw.target_distance_km)}
                {/if}
                {#if pw.target_pace_description}
                  &middot; {pw.target_pace_description} pace
                {/if}
              </div>
            </div>
            {#if isToday}
              <span class="text-xs font-medium text-primary-500">TODAY</span>
            {:else if isPast && !pw.completed && pw.workout_type !== 'rest'}
              <span class="text-xs text-red-400">missed</span>
            {/if}
          </button>
        {/each}
        {#if thisWeekWorkouts.length === 0}
          <p class="text-gray-400 text-sm text-center py-4">No workouts scheduled this week</p>
        {/if}
      </div>
    </div>

    <!-- Weekly Progress Charts -->
    {#if progress.length > 0}
      <div class="card p-6 mb-6">
        <h2 class="text-sm font-semibold text-gray-500 mb-4">Weekly Run Mileage</h2>
        <div class="flex items-center gap-4 mb-3 text-[10px] text-gray-400">
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-primary-300"></span> Planned</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-green-500"></span> Actual</span>
        </div>
        <div class="flex items-end gap-1 h-32 overflow-x-auto">
          {#each progress as week}
            {@const plannedH = maxRunKm > 0 ? (week.planned_run_km / maxRunKm) * 100 : 0}
            {@const actualH = maxRunKm > 0 ? (week.actual_run_km / maxRunKm) * 100 : 0}
            {@const isCurrent = week.week_number === currentWeek}
            <div class="flex-1 min-w-[28px] flex flex-col items-center gap-0.5">
              <div class="w-full flex items-end gap-0.5" style="height: 96px;">
                <div
                  class="flex-1 rounded-t-sm {isCurrent ? 'bg-primary-400' : 'bg-primary-200 dark:bg-primary-800'}"
                  style="height: {Math.max(plannedH, 2)}%;"
                ></div>
                <div
                  class="flex-1 rounded-t-sm {isCurrent ? 'bg-green-500' : 'bg-green-300 dark:bg-green-800'}"
                  style="height: {Math.max(actualH, week.actual_run_km > 0 ? 2 : 0)}%;"
                ></div>
              </div>
              <span class="text-[9px] {isCurrent ? 'text-primary-500 font-bold' : 'text-gray-400'}">
                W{week.week_number}
              </span>
            </div>
          {/each}
        </div>
      </div>

      {#if hasBikeData}
        <div class="card p-6 mb-6">
          <h2 class="text-sm font-semibold text-gray-500 mb-4">Weekly Bike Mileage</h2>
          <div class="flex items-center gap-4 mb-3 text-[10px] text-gray-400">
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-teal-300"></span> Planned</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-teal-600"></span> Actual</span>
          </div>
          <div class="flex items-end gap-1 h-32 overflow-x-auto">
            {#each progress as week}
              {@const plannedH = maxBikeKm > 0 ? (week.planned_bike_km / maxBikeKm) * 100 : 0}
              {@const actualH = maxBikeKm > 0 ? (week.actual_bike_km / maxBikeKm) * 100 : 0}
              {@const isCurrent = week.week_number === currentWeek}
              <div class="flex-1 min-w-[28px] flex flex-col items-center gap-0.5">
                <div class="w-full flex items-end gap-0.5" style="height: 96px;">
                  <div
                    class="flex-1 rounded-t-sm {isCurrent ? 'bg-teal-400' : 'bg-teal-200 dark:bg-teal-800'}"
                    style="height: {Math.max(plannedH, 2)}%;"
                  ></div>
                  <div
                    class="flex-1 rounded-t-sm {isCurrent ? 'bg-teal-600' : 'bg-teal-400 dark:bg-teal-700'}"
                    style="height: {Math.max(actualH, week.actual_bike_km > 0 ? 2 : 0)}%;"
                  ></div>
                </div>
                <span class="text-[9px] {isCurrent ? 'text-primary-500 font-bold' : 'text-gray-400'}">
                  W{week.week_number}
                </span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    {/if}

    <!-- Full Schedule (collapsible weeks) -->
    <div class="card p-6">
      <h2 class="text-sm font-semibold text-gray-500 mb-4">Full Schedule</h2>
      <div class="space-y-2">
        {#each Array.from(new Set(activePlan.planned_workouts.map(w => w.week_number))).sort((a, b) => a - b) as weekNum}
          {@const weekWorkouts = activePlan.planned_workouts.filter(w => w.week_number === weekNum)}
          {@const completedCount = weekWorkouts.filter(w => w.completed).length}
          {@const weekRunKm = weekWorkouts.filter(w => w.workout_type !== 'bike').reduce((s, w) => s + (w.target_distance_km || 0), 0)}
          {@const weekBikeKm = weekWorkouts.filter(w => w.workout_type === 'bike').reduce((s, w) => s + (w.target_distance_km || 0), 0)}
          {@const weekProgress = progress.find(p => p.week_number === weekNum)}
          {@const actualRunKm = weekProgress?.actual_run_km || 0}
          {@const actualBikeKm = weekProgress?.actual_bike_km || 0}
          {@const isCurrent = weekNum === currentWeek}
          {@const isPast = weekNum < currentWeek}
          {@const weekStart = weekWorkouts.length > 0 ? format(parseISO(weekWorkouts[0].date), 'MMM d') : ''}
          {@const weekEnd = weekWorkouts.length > 0 ? format(parseISO(weekWorkouts[weekWorkouts.length - 1].date), 'MMM d') : ''}
          <div class={clsx(isPast && !isCurrent ? 'opacity-50' : '')}>
            <button
              on:click={() => toggleWeekExpand(weekNum)}
              class={clsx(
                'w-full p-3 rounded-lg text-left',
                isCurrent ? 'bg-primary-50 dark:bg-primary-900/20' : 'bg-gray-50 dark:bg-gray-700/50',
                'hover:bg-gray-100 dark:hover:bg-gray-700'
              )}
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class={clsx('text-sm font-medium', isCurrent ? 'text-primary-600' : '')}>
                    Week {weekNum}
                  </span>
                  <span class="text-[10px] text-gray-400">{weekStart} – {weekEnd}</span>
                  {#if isCurrent}
                    <span class="text-[10px] bg-primary-500 text-white px-1.5 py-0.5 rounded-full">current</span>
                  {/if}
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400">{completedCount}/{weekWorkouts.length}</span>
                  <ChevronDown size={14} class={clsx('text-gray-400 transition-transform', expandedWeek === weekNum ? 'rotate-180' : '')} />
                </div>
              </div>
              <div class="flex items-center gap-4 mt-1.5 text-xs">
                <span class="flex items-center gap-1.5 text-gray-400">
                  <PersonStanding size={13} />
                  <span>{distFmt(weekRunKm)}</span>
                  {#if actualRunKm > 0 || isPast}
                    <span class={clsx('font-medium', actualRunKm >= weekRunKm * 0.8 ? 'text-green-500' : 'text-red-400')}>
                      {distFmt(actualRunKm)}
                    </span>
                  {/if}
                </span>
                {#if weekBikeKm > 0}
                  <span class="flex items-center gap-1.5 text-teal-400">
                    <Bike size={13} />
                    <span>{distFmt(weekBikeKm)}</span>
                    {#if actualBikeKm > 0 || isPast}
                      <span class={clsx('font-medium', actualBikeKm >= weekBikeKm * 0.8 ? 'text-teal-500' : 'text-red-400')}>
                        {distFmt(actualBikeKm)}
                      </span>
                    {/if}
                  </span>
                {/if}
              </div>
            </button>
            {#if expandedWeek === weekNum}
              <!-- Column headers -->
              <div class="grid grid-cols-[auto_1fr_80px_80px_auto] gap-2 px-4 pt-2 pb-1 text-[10px] text-gray-400 uppercase tracking-wide">
                <span></span>
                <span>Planned</span>
                <span class="text-right">Target</span>
                <span class="text-right">Achieved</span>
                <span></span>
              </div>
              <div class="pl-4 space-y-1">
                {#each weekWorkouts as pw}
                  {@const pwPast = pw.date < todayStr}
                  {#if editingWorkout === pw.id}
                    <!-- Edit mode -->
                    <div class="flex flex-wrap items-center gap-2 p-2 rounded bg-gray-50 dark:bg-gray-700/50">
                      <select bind:value={editType} class="text-xs border rounded px-1 py-1 dark:bg-gray-700 dark:border-gray-600">
                        {#each WORKOUT_TYPES as wt}
                          <option value={wt}>{wt.replace('_', ' ')}</option>
                        {/each}
                      </select>
                      <input bind:value={editDesc} class="text-sm border rounded px-2 py-1 flex-1 min-w-[100px] dark:bg-gray-700 dark:border-gray-600" placeholder="Description" />
                      <input bind:value={editDist} type="number" step="0.1" class="text-sm border rounded px-2 py-1 w-20 dark:bg-gray-700 dark:border-gray-600" placeholder={getDistanceLabel($settings.distance_unit)} />
                      <span class="text-xs text-gray-400">{getDistanceLabel($settings.distance_unit)}</span>
                      <button on:click={() => saveEdit(pw)} class="text-xs text-primary-500 font-medium">Save</button>
                      <button on:click={() => { editingWorkout = null; }} class="text-xs text-gray-400">Cancel</button>
                    </div>
                  {:else}
                    <!-- View mode: grid layout -->
                    <div class="grid grid-cols-[auto_1fr_80px_80px_auto] gap-2 items-center p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700/50">
                      <button on:click={() => toggleWorkout(pw)} class="flex-shrink-0">
                        {#if pw.completed}
                          <CheckCircle size={16} class="text-green-500" />
                        {:else}
                          <Circle size={16} class={clsx(pwPast && pw.workout_type !== 'rest' ? 'text-red-300' : 'text-gray-300')} />
                        {/if}
                      </button>
                      <div class="min-w-0">
                        <div class="flex items-center gap-1.5">
                          <span class="text-xs text-gray-400">{format(parseISO(pw.date), 'EEE d')}</span>
                          <span class={clsx('text-[10px] px-1.5 py-0.5 rounded', WORKOUT_COLORS[pw.workout_type] || WORKOUT_COLORS.run)}>
                            {pw.workout_type.replace('_', ' ')}
                          </span>
                          <span class="text-sm truncate">{pw.description}</span>
                        </div>
                      </div>
                      <span class="text-xs text-gray-400 text-right">{pw.target_distance_km ? distFmt(pw.target_distance_km) : '—'}</span>
                      <span class="text-xs text-right {pw.completed ? 'text-green-500 font-medium' : 'text-gray-300'}">{pw.completed ? (pw.actual_distance_km ? distFmt(pw.actual_distance_km) : 'Done') : '—'}</span>
                      <button on:click|stopPropagation={() => startEdit(pw)} class="text-xs text-gray-400 hover:text-primary-500">edit</button>
                    </div>
                  {/if}
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    </div>

  {:else}
    <!-- No Active Plan - Create New -->
    <div class="card p-6 mb-6">
      <h2 class="text-lg font-semibold mb-4">Start a Training Plan</h2>
      <p class="text-sm text-gray-500 mb-4">Pick your race distance and date. A progressive training schedule will be generated based on the time available.</p>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label for="race-distance" class="label">Race Distance</label>
          <div class="grid grid-cols-2 gap-2">
            {#each distances as dist}
              <button
                on:click={() => { selectedDistance = dist.id; }}
                class={clsx(
                  'p-3 rounded-lg border-2 text-left transition-all',
                  selectedDistance === dist.id
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-gray-200 dark:border-gray-700 hover:border-primary-300'
                )}
              >
                <div class="font-semibold text-sm">{dist.label}</div>
                <div class="text-xs text-gray-400">{dist.min_weeks}-{dist.max_weeks} weeks</div>
              </button>
            {/each}
          </div>
        </div>
        <div>
          <label for="race-date" class="label">Race Date</label>
          <input
            id="race-date"
            type="date"
            bind:value={raceDate}
            min={format(new Date(), 'yyyy-MM-dd')}
            class="input mb-3"
          />
          {#if raceDate}
            {@const weeksAway = Math.floor((new Date(raceDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24 * 7))}
            <p class="text-xs text-gray-400 mb-3">{weeksAway} weeks away</p>
          {/if}

          <span class="label">Training Start</span>
          <div class="flex gap-2 mb-2">
            {#each START_MODE_OPTIONS as [val, label]}
              <button
                on:click={() => { startMode = val; }}
                class={clsx('px-3 py-1 rounded text-xs', startMode === val ? 'bg-primary-500 text-white' : 'bg-gray-100 dark:bg-gray-700')}
              >{label}</button>
            {/each}
          </div>
          {#if startMode === 'auto'}
            <p class="text-xs text-gray-400">Starts from today, auto-fits to available time.</p>
          {:else if startMode === 'weeks'}
            <input type="number" bind:value={totalWeeks} min="4" max="52" class="input" />
            {#if raceDate}
              {@const computedStart = new Date(new Date(raceDate).getTime() - totalWeeks * 7 * 24 * 60 * 60 * 1000)}
              <p class="text-xs text-gray-400 mt-1">Starts {format(computedStart, 'MMM d, yyyy')}</p>
            {/if}
          {:else}
            <input type="date" bind:value={startDate} max={raceDate} class="input" />
            {#if startDate && raceDate}
              {@const computedWeeks = Math.floor((new Date(raceDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24 * 7))}
              <p class="text-xs text-gray-400 mt-1">{computedWeeks} weeks of training</p>
            {/if}
          {/if}
        </div>
      </div>

      <!-- Terrain -->
      <div class="mb-4">
        <span class="label">Terrain</span>
        <div class="flex gap-2">
          {#each ['road', 'trail', 'mixed'] as t}
            <button
              on:click={() => { selectedTerrain = t; }}
              class={clsx(
                'px-4 py-2 rounded-lg border-2 text-sm transition-all',
                selectedTerrain === t
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 font-medium'
                  : 'border-gray-200 dark:border-gray-700 hover:border-primary-300'
              )}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          {/each}
        </div>
      </div>

      <!-- Bike cross-training -->
      <div class="mb-4">
        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" bind:checked={includeBike} class="rounded" />
          Include bike cross-training
        </label>
        {#if includeBike}
          <div class="mt-2 flex items-center gap-3">
            <span class="text-xs text-gray-400">Light</span>
            <input type="range" min="10" max="100" step="10" bind:value={bikeIntensity} class="flex-1" />
            <span class="text-xs text-gray-400">Heavy</span>
            <span class="text-xs font-medium w-10 text-right">{bikeIntensity}%</span>
          </div>
        {/if}
      </div>

      <!-- Rest days -->
      <div class="mb-4">
        <span class="label">Rest Days per Week</span>
        <div class="flex gap-2">
          {#each [1, 2, 3] as n}
            <button
              on:click={() => { restDays = n; }}
              class={clsx(
                'px-4 py-2 rounded-lg border-2 text-sm transition-all',
                restDays === n
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 font-medium'
                  : 'border-gray-200 dark:border-gray-700 hover:border-primary-300'
              )}
            >
              {n} day{n > 1 ? 's' : ''}
            </button>
          {/each}
        </div>
        <p class="text-xs text-gray-400 mt-1">{7 - restDays} active days per week</p>
      </div>

      <button
        on:click={createPlan}
        disabled={creating || !selectedDistance || !raceDate}
        class="btn btn-primary"
      >
        {creating ? 'Creating...' : 'Generate Plan'}
      </button>
      {#if errorMessage}
        <p class="text-sm text-red-500 mt-2">{errorMessage}</p>
      {/if}
    </div>

    <!-- Past Plans -->
    {#if plans.filter(p => p.status !== 'active').length > 0}
      <div class="card p-6">
        <h2 class="text-sm font-semibold text-gray-500 mb-3">Past Plans</h2>
        <div class="space-y-2">
          {#each plans.filter(p => p.status !== 'active') as plan}
            <div class="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div>
                <span class="text-sm font-medium">{plan.plan_display_name}</span>
                <span class="text-xs text-gray-400 ml-2">
                  Race: {format(parseISO(plan.race_date), 'MMM d, yyyy')}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <span class={clsx(
                  'text-xs px-2 py-0.5 rounded-full',
                  plan.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-500'
                )}>
                  {plan.status}
                </span>
                <button
                  on:click={async () => {
                    if (!confirm('Delete this plan?')) return;
                    await api.deleteTrainingPlan(plan.id);
                    await loadData();
                  }}
                  class="text-xs text-red-400 hover:text-red-600"
                >delete</button>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>
