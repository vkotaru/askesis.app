<script lang="ts">
  import { onMount } from 'svelte';
  import { format, subDays, parseISO, startOfWeek, endOfWeek, addWeeks, addDays, isSameWeek } from 'date-fns';
  import { ChevronLeft, ChevronRight, X, Flame, Beef, Footprints, Activity as ActivityIcon } from 'lucide-svelte';
  import { api, type DailyLog, type Activity as ActivityType, type Meal, type DailyNutrition, type TrainingPlan } from '$lib/api/client';
  import { offlineApi } from '$lib/stores/data';
  import { settings } from '$lib/stores/settings';
  import { distanceFromMetric } from '$lib/utils/units';
  import {
    MetricSnapshotCard,
    TodayNutritionCard,
    WeightTrendCard,
    RecentActivitiesCard,
    NutritionChartCard,
    RaceCountdownCard,
    WeeklyTrainingCard,
    StepsBarCard,
  } from '$lib/components/cards';

  // Global (non-week-scoped) data
  let logs: DailyLog[] = [];
  let recentActivities: ActivityType[] = [];
  let allActivities: ActivityType[] = [];
  let activePlanData: TrainingPlan | null = null;

  // Week-scoped data
  let weekMeals: Meal[] = [];
  let weekNutrition: DailyNutrition[] = [];
  let weekActivities: ActivityType[] = [];
  let weekLogs: DailyLog[] = [];

  let loading = true;
  let weekLoading = false;
  let selectedDay: string | null = null;

  const today = format(new Date(), 'yyyy-MM-dd');
  const sixtyDaysAgo = format(subDays(new Date(), 60), 'yyyy-MM-dd');

  // Week state — starts at current week (Mon)
  let selectedWeekStart: Date = startOfWeek(new Date(), { weekStartsOn: 1 });

  $: weekStartStr = format(selectedWeekStart, 'yyyy-MM-dd');
  $: weekEndStr = format(endOfWeek(selectedWeekStart, { weekStartsOn: 1 }), 'yyyy-MM-dd');
  $: weekDates = Array.from({ length: 7 }, (_, i) => format(addDays(selectedWeekStart, i), 'yyyy-MM-dd'));
  $: weekRangeLabel = `${format(selectedWeekStart, 'MMM d')} – ${format(addDays(selectedWeekStart, 6), 'MMM d, yyyy')}`;
  $: isCurrentWeek = isSameWeek(selectedWeekStart, new Date(), { weekStartsOn: 1 });

  function prevWeek() {
    selectedWeekStart = addWeeks(selectedWeekStart, -1);
  }
  function nextWeek() {
    if (isCurrentWeek) return;
    selectedWeekStart = addWeeks(selectedWeekStart, 1);
  }
  function thisWeek() {
    selectedWeekStart = startOfWeek(new Date(), { weekStartsOn: 1 });
  }

  async function loadWeek(start: string, end: string) {
    weekLoading = true;
    try {
      const [mealsData, nutritionData, activitiesData, logsData] = await Promise.all([
        offlineApi.getMeals(undefined, undefined, start, end, 500),
        offlineApi.getNutritionHistory(start, end, undefined, 14),
        offlineApi.getActivities(start, end, undefined, 200),
        offlineApi.getDailyLogs(start, end, undefined, 14),
      ]);
      weekMeals = mealsData;
      weekNutrition = nutritionData;
      weekActivities = activitiesData;
      weekLogs = logsData;
    } catch (err) {
      console.error('Failed to load week data:', err);
    } finally {
      weekLoading = false;
    }
  }

  // Reactive reload when week changes
  $: if (weekStartStr && weekEndStr) {
    loadWeek(weekStartStr, weekEndStr);
  }

  onMount(async () => {
    try {
      const [logsData, recentData, allActsData] = await Promise.all([
        offlineApi.getDailyLogs(undefined, undefined, undefined, 365),
        offlineApi.getActivities(undefined, undefined, undefined, 10),
        offlineApi.getActivities(sixtyDaysAgo, today, undefined, 500),
      ]);
      logs = logsData;
      recentActivities = recentData;
      allActivities = allActsData;

      try {
        const plans = await api.getTrainingPlans();
        activePlanData = plans.find(p => p.status === 'active') || null;
      } catch {
        activePlanData = null;
      }
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      loading = false;
    }
  });

  // Weight trend — all logs
  $: weightPoints = logs
    .filter(l => l.weight)
    .reverse()
    .map(l => ({ date: l.date, weight: l.weight! }));

  // Per-day maps for selected week
  $: dailyCaloriesMap = weekMeals.reduce((acc, meal) => {
    acc[meal.date] = (acc[meal.date] || 0) + (meal.calories || 0);
    return acc;
  }, {} as Record<string, number>);

  $: dailyNutritionMap = weekNutrition.reduce((acc, n) => {
    acc[n.date] = n;
    return acc;
  }, {} as Record<string, DailyNutrition>);

  $: dailyBurnedMap = weekActivities.reduce((acc, a) => {
    if (a.calories) acc[a.date] = (acc[a.date] || 0) + a.calories;
    return acc;
  }, {} as Record<string, number>);

  $: nutritionChartData = weekDates.map(date => ({
    date,
    calories: dailyCaloriesMap[date] || 0,
    protein: dailyNutritionMap[date]?.protein_g || 0,
    burnedCalories: dailyBurnedMap[date] || 0,
  }));

  $: stepsData = weekDates.map(date => {
    const log = weekLogs.find(l => l.date === date);
    return { date, steps: log?.steps ?? null };
  });

  // Week totals
  $: weekTotalCalories = Object.values(dailyCaloriesMap).reduce((s, v) => s + v, 0);
  $: weekProteinAvg = (() => {
    const vals = weekNutrition.map(n => n.protein_g || 0).filter(v => v > 0);
    return vals.length > 0 ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : undefined;
  })();
  $: weekCarbsAvg = (() => {
    const vals = weekNutrition.map(n => n.carbs_g || 0).filter(v => v > 0);
    return vals.length > 0 ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : undefined;
  })();
  $: weekFatAvg = (() => {
    const vals = weekNutrition.map(n => n.fat_g || 0).filter(v => v > 0);
    return vals.length > 0 ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : undefined;
  })();
  $: weekCaloriesAvg = Math.round(weekTotalCalories / 7);

  // Day summary for modal
  $: daySummary = selectedDay ? {
    date: selectedDay,
    meals: weekMeals.filter(m => m.date === selectedDay).sort((a, b) => (a.time || '').localeCompare(b.time || '')),
    nutrition: dailyNutritionMap[selectedDay] || null,
    log: weekLogs.find(l => l.date === selectedDay) || null,
    activities: weekActivities.filter(a => a.date === selectedDay),
    calories: dailyCaloriesMap[selectedDay] || 0,
    burned: dailyBurnedMap[selectedDay] || 0,
  } : null;

  function openDay(e: CustomEvent<string>) {
    selectedDay = e.detail;
  }
  function closeDay() {
    selectedDay = null;
  }

  // Weekly training multi-week data (unchanged)
  function isBikeActivity(name: string): boolean {
    const lower = name.toLowerCase();
    return lower.includes('bike') || lower.includes('cycling') || lower.includes('ride') || lower.includes('cycle');
  }

  function isRunActivity(name: string): boolean {
    const lower = name.toLowerCase();
    return lower.includes('run') || lower.includes('running') || lower.includes('jog');
  }

  function getWeeks(numWeeks: number): { start: Date; end: Date; label: string }[] {
    const weeks: { start: Date; end: Date; label: string }[] = [];
    const now = new Date();
    const currentWeekStart = startOfWeek(now, { weekStartsOn: 1 });
    for (let i = numWeeks - 1; i >= 0; i--) {
      const ws = addWeeks(currentWeekStart, -i);
      const we = endOfWeek(ws, { weekStartsOn: 1 });
      weeks.push({ start: ws, end: we, label: format(ws, 'MMM d') });
    }
    return weeks;
  }

  $: weeks = getWeeks(8);

  $: weeklyTrainingData = weeks.map(week => {
    const wa = allActivities.filter(a => {
      const actDate = parseISO(a.date);
      return actDate >= week.start && actDate <= week.end;
    });
    return {
      label: week.label,
      bikeMiles: Math.round(wa
        .filter(a => isBikeActivity(a.name) && a.distance_km)
        .reduce((sum, a) => sum + distanceFromMetric(a.distance_km || 0, $settings.distance_unit), 0) * 10) / 10,
      roadMiles: Math.round(wa
        .filter(a => isRunActivity(a.name) && a.distance_km)
        .reduce((sum, a) => sum + distanceFromMetric(a.distance_km || 0, $settings.distance_unit), 0) * 10) / 10,
      strengthCount: wa.filter(a => a.activity_type === 'strength').length,
    };
  });
</script>

<svelte:head>
  <title>Dashboard - Askesis</title>
</svelte:head>

<div>
  <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
    <div>
      <h1 class="text-2xl font-bold">Dashboard</h1>
      <p class="text-gray-500 text-sm mt-1">{weekRangeLabel}</p>
    </div>
    <div class="flex items-center gap-2">
      <button
        type="button"
        class="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
        on:click={prevWeek}
        aria-label="Previous week"
      >
        <ChevronLeft size={18} />
      </button>
      <button
        type="button"
        class="px-3 py-1.5 text-sm rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
        on:click={thisWeek}
        disabled={isCurrentWeek}
      >
        This week
      </button>
      <button
        type="button"
        class="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
        on:click={nextWeek}
        disabled={isCurrentWeek}
        aria-label="Next week"
      >
        <ChevronRight size={18} />
      </button>
    </div>
  </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else}
    <div class="mb-8">
      <MetricSnapshotCard {logs} />
    </div>

    <div class="mb-8">
      <TodayNutritionCard
        title="Week Avg / Totals — {weekCaloriesAvg} cal/day"
        calories={weekTotalCalories}
        protein_g={weekProteinAvg}
        carbs_g={weekCarbsAvg}
        fat_g={weekFatAvg}
      />
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 relative">
      {#if weekLoading}
        <div class="absolute inset-0 bg-white/40 dark:bg-black/30 z-20 rounded-lg flex items-center justify-center pointer-events-none">
          <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
        </div>
      {/if}

      <NutritionChartCard
        data={nutritionChartData}
        subtitle="Click a day for details"
        calorieTarget={$settings.calorie_target}
        proteinTarget={$settings.protein_target}
        on:dayClick={openDay}
      />

      <StepsBarCard
        steps={stepsData}
        subtitle="Click a day for details"
        on:dayClick={openDay}
      />

      <WeightTrendCard
        {weightPoints}
        weightUnit={$settings.weight_unit}
        showRangeSelector={true}
        showMovingAverage={true}
        interactive={true}
      />

      <RecentActivitiesCard
        activities={recentActivities}
        distanceUnit={$settings.distance_unit}
      />

      {#if activePlanData}
        <RaceCountdownCard plan={activePlanData} />
      {/if}

      <WeeklyTrainingCard
        weeklyData={weeklyTrainingData}
        distanceLabel={$settings.distance_unit}
      />
    </div>
  {/if}
</div>

<!-- Day detail modal -->
{#if selectedDay && daySummary}
  <div
    class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
    on:click={closeDay}
    on:keydown={(e) => e.key === 'Escape' && closeDay()}
    role="presentation"
  >
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="bg-white dark:bg-gray-900 rounded-lg max-w-md w-full max-h-[85vh] overflow-y-auto shadow-xl"
      on:click|stopPropagation
      role="dialog"
      aria-modal="true"
    >
      <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h3 class="text-lg font-semibold">{format(parseISO(selectedDay), 'EEEE, MMM d')}</h3>
          <p class="text-xs text-gray-400">{format(parseISO(selectedDay), 'yyyy-MM-dd')}</p>
        </div>
        <button
          type="button"
          class="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
          on:click={closeDay}
          aria-label="Close"
        >
          <X size={18} />
        </button>
      </div>

      <div class="p-4 space-y-4">
        <!-- Nutrition summary -->
        <div>
          <div class="flex items-center gap-2 mb-2">
            <Flame size={16} class="text-nutrition-500" />
            <h4 class="text-sm font-medium">Nutrition</h4>
          </div>
          <div class="grid grid-cols-4 gap-2 text-center">
            <div>
              <p class="text-[10px] text-gray-400">Calories</p>
              <p class="text-base font-semibold">{daySummary.calories || '—'}</p>
            </div>
            <div>
              <p class="text-[10px] text-gray-400">Protein</p>
              <p class="text-base font-semibold">
                {daySummary.nutrition?.protein_g ?? '—'}{#if daySummary.nutrition?.protein_g}<span class="text-[10px] text-gray-400">g</span>{/if}
              </p>
            </div>
            <div>
              <p class="text-[10px] text-gray-400">Carbs</p>
              <p class="text-base font-semibold">
                {daySummary.nutrition?.carbs_g ?? '—'}{#if daySummary.nutrition?.carbs_g}<span class="text-[10px] text-gray-400">g</span>{/if}
              </p>
            </div>
            <div>
              <p class="text-[10px] text-gray-400">Fat</p>
              <p class="text-base font-semibold">
                {daySummary.nutrition?.fat_g ?? '—'}{#if daySummary.nutrition?.fat_g}<span class="text-[10px] text-gray-400">g</span>{/if}
              </p>
            </div>
          </div>
        </div>

        <!-- Meals -->
        {#if daySummary.meals.length > 0}
          <div>
            <h4 class="text-sm font-medium mb-2">Meals ({daySummary.meals.length})</h4>
            <ul class="space-y-1.5">
              {#each daySummary.meals as meal}
                <li class="flex items-center justify-between text-xs border-b border-gray-100 dark:border-gray-800 pb-1.5">
                  <div class="flex-1 min-w-0">
                    <span class="font-medium">{meal.label || 'Meal'}</span>
                    {#if meal.time}<span class="text-gray-400 ml-1">{meal.time}</span>{/if}
                  </div>
                  <span class="text-orange-500 font-medium ml-2">{meal.calories || 0} cal</span>
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        <!-- Steps / daily log -->
        {#if daySummary.log}
          <div>
            <div class="flex items-center gap-2 mb-2">
              <Footprints size={16} class="text-cardio-500" />
              <h4 class="text-sm font-medium">Daily Log</h4>
            </div>
            <div class="grid grid-cols-3 gap-2 text-center">
              <div>
                <p class="text-[10px] text-gray-400">Steps</p>
                <p class="text-sm font-semibold">{daySummary.log.steps?.toLocaleString() ?? '—'}</p>
              </div>
              <div>
                <p class="text-[10px] text-gray-400">Sleep</p>
                <p class="text-sm font-semibold">{daySummary.log.sleep_hours ?? '—'}{#if daySummary.log.sleep_hours}<span class="text-[10px] text-gray-400">h</span>{/if}</p>
              </div>
              <div>
                <p class="text-[10px] text-gray-400">Water</p>
                <p class="text-sm font-semibold">{daySummary.log.water_ml ?? '—'}{#if daySummary.log.water_ml}<span class="text-[10px] text-gray-400">ml</span>{/if}</p>
              </div>
            </div>
          </div>
        {/if}

        <!-- Activities -->
        {#if daySummary.activities.length > 0}
          <div>
            <div class="flex items-center gap-2 mb-2">
              <ActivityIcon size={16} class="text-strength-500" />
              <h4 class="text-sm font-medium">Activities ({daySummary.activities.length})</h4>
              {#if daySummary.burned > 0}
                <span class="text-[10px] text-red-400 ml-auto">{daySummary.burned} cal burned</span>
              {/if}
            </div>
            <ul class="space-y-1.5">
              {#each daySummary.activities as act}
                <li class="flex items-center justify-between text-xs border-b border-gray-100 dark:border-gray-800 pb-1.5">
                  <div class="flex-1 min-w-0">
                    <span class="font-medium">{act.name}</span>
                    {#if act.duration_mins}<span class="text-gray-400 ml-1">{act.duration_mins}m</span>{/if}
                  </div>
                  {#if act.distance_km}
                    <span class="text-gray-500 ml-2">{distanceFromMetric(act.distance_km, $settings.distance_unit).toFixed(1)} {$settings.distance_unit}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if daySummary.meals.length === 0 && !daySummary.log && daySummary.activities.length === 0}
          <p class="text-sm text-gray-400 text-center py-4">No data for this day</p>
        {/if}
      </div>
    </div>
  </div>
{/if}

