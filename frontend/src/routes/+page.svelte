<script lang="ts">
  import { onMount } from 'svelte';
  import { format, subDays, parseISO, startOfWeek, endOfWeek, addWeeks } from 'date-fns';
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
  } from '$lib/components/cards';

  let logs: DailyLog[] = [];
  let activities: ActivityType[] = [];
  let allActivities: ActivityType[] = [];
  let todayMeals: Meal[] = [];
  let mealsHistory: Meal[] = [];
  let nutritionHistory: DailyNutrition[] = [];
  let todayNutrition: DailyNutrition | null = null;
  let activePlanData: TrainingPlan | null = null;
  let loading = true;

  const today = format(new Date(), 'yyyy-MM-dd');
  const thirtyDaysAgo = format(subDays(new Date(), 30), 'yyyy-MM-dd');
  const sixtyDaysAgo = format(subDays(new Date(), 60), 'yyyy-MM-dd');

  onMount(async () => {
    try {
      const [logsData, activitiesData, allActivitiesData, mealsData, mealsHistoryData, nutritionHistoryData] = await Promise.all([
        offlineApi.getDailyLogs(undefined, undefined, undefined, 365),
        offlineApi.getActivities(undefined, undefined, undefined, 10),
        offlineApi.getActivities(sixtyDaysAgo, today, undefined, 500),
        offlineApi.getMeals(today),
        offlineApi.getMeals(undefined, undefined, thirtyDaysAgo, today, 500),
        offlineApi.getNutritionHistory(thirtyDaysAgo, today, undefined, 60),
      ]);
      logs = logsData;
      activities = activitiesData;
      allActivities = allActivitiesData;
      todayMeals = mealsData;
      mealsHistory = mealsHistoryData;
      nutritionHistory = nutritionHistoryData;

      try {
        todayNutrition = await offlineApi.getDailyNutrition(today);
      } catch {
        todayNutrition = null;
      }

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

  $: todayCalories = todayMeals.reduce((sum, m) => sum + (m.calories || 0), 0);

  // Weight trend data
  $: weightPoints = logs
    .filter(l => l.weight)
    .reverse()
    .map(l => ({ date: l.date, weight: l.weight! }));

  // Nutrition chart data
  $: dailyCaloriesMap = mealsHistory.reduce((acc, meal) => {
    acc[meal.date] = (acc[meal.date] || 0) + (meal.calories || 0);
    return acc;
  }, {} as Record<string, number>);

  $: dailyProteinMap = nutritionHistory.reduce((acc, n) => {
    acc[n.date] = n.protein_g || 0;
    return acc;
  }, {} as Record<string, number>);

  $: nutritionDates = [...new Set([...Object.keys(dailyCaloriesMap), ...Object.keys(dailyProteinMap)])]
    .sort().slice(-30);

  $: nutritionChartData = nutritionDates.map(date => ({
    date,
    calories: dailyCaloriesMap[date] || 0,
    protein: dailyProteinMap[date] || 0,
  }));

  // Weekly training data
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
    const weekActivities = allActivities.filter(a => {
      const actDate = parseISO(a.date);
      return actDate >= week.start && actDate <= week.end;
    });
    return {
      label: week.label,
      bikeMiles: Math.round(weekActivities
        .filter(a => isBikeActivity(a.name) && a.distance_km)
        .reduce((sum, a) => sum + distanceFromMetric(a.distance_km || 0, $settings.distance_unit), 0) * 10) / 10,
      roadMiles: Math.round(weekActivities
        .filter(a => isRunActivity(a.name) && a.distance_km)
        .reduce((sum, a) => sum + distanceFromMetric(a.distance_km || 0, $settings.distance_unit), 0) * 10) / 10,
      strengthCount: weekActivities.filter(a => a.activity_type === 'strength').length,
    };
  });
</script>

<svelte:head>
  <title>Dashboard - Askesis</title>
</svelte:head>

<div>
  <div class="mb-8">
    <h1 class="text-2xl font-bold">Dashboard</h1>
    <p class="text-gray-500 text-sm mt-1">
      {format(new Date(), 'EEEE, MMMM d, yyyy')}
    </p>
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
        calories={todayCalories}
        protein_g={todayNutrition?.protein_g}
        carbs_g={todayNutrition?.carbs_g}
        fat_g={todayNutrition?.fat_g}
      />
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <WeightTrendCard
        {weightPoints}
        weightUnit={$settings.weight_unit}
        showRangeSelector={true}
        showMovingAverage={true}
        interactive={true}
      />

      <RecentActivitiesCard
        {activities}
        distanceUnit={$settings.distance_unit}
      />

      <NutritionChartCard data={nutritionChartData} subtitle="Last 30 days" />

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
