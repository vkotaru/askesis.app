<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { format, parseISO, addDays } from 'date-fns';
  import '../../../app.css';

  interface WeightPoint {
    date: string;
    weight: number;
  }

  interface ActivityEntry {
    date: string;
    name: string;
    activity_type: string;
    duration_mins: number | null;
    calories: number | null;
    icon: string | null;
  }

  interface MeasurementSnapshot {
    date: string;
    neck: number | null;
    shoulders: number | null;
    chest: number | null;
    bicep_left: number | null;
    bicep_right: number | null;
    waist: number | null;
    abdomen: number | null;
    hips: number | null;
    thigh_left: number | null;
    thigh_right: number | null;
    calf_left: number | null;
    calf_right: number | null;
  }

  interface NutritionAverage {
    avg_calories: number | null;
    avg_protein_g: number | null;
    avg_carbs_g: number | null;
    avg_fat_g: number | null;
    days_tracked: number;
  }

  interface Report {
    today: string;
    latest_weight: number | null;
    latest_weight_date: string | null;
    weight_unit: string;
    weight_trend: WeightPoint[];
    week_activities: ActivityEntry[];
    week_start: string;
    week_end: string;
    latest_measurements: MeasurementSnapshot | null;
    nutrition_avg: NutritionAverage | null;
    generated_at: string;
  }

  let report: Report | null = null;
  let loading = true;
  let error = '';

  // Chart dimensions
  const chartWidth = 600;
  const chartHeight = 300;
  const padding = { top: 20, right: 20, bottom: 30, left: 55 };

  $: token = $page.params.token;

  $: weightData = report?.weight_trend ?? [];

  $: plotWidth = chartWidth - padding.left - padding.right;
  $: plotHeight = chartHeight - padding.top - padding.bottom;

  $: weights = weightData.map(d => d.weight);
  $: minWeight = weights.length > 0 ? Math.min(...weights) - 0.5 : 0;
  $: maxWeight = weights.length > 0 ? Math.max(...weights) + 0.5 : 100;
  $: weightRange = maxWeight - minWeight || 1;

  $: xScale = (i: number) => padding.left + (i / Math.max(weightData.length - 1, 1)) * plotWidth;
  $: yScale = (w: number) => padding.top + plotHeight - ((w - minWeight) / weightRange) * plotHeight;

  $: linePath = weightData.length > 1
    ? 'M ' + weightData.map((d, i) => `${xScale(i)},${yScale(d.weight)}`).join(' L ')
    : '';

  $: yTicks = (() => {
    const tickCount = 5;
    const step = weightRange / (tickCount - 1);
    return Array.from({ length: tickCount }, (_, i) => {
      const value = minWeight + step * i;
      return { value, y: yScale(value) };
    });
  })();

  // Week calendar
  $: weekDays = (() => {
    if (!report) return [];
    const start = parseISO(report.week_start);
    return Array.from({ length: 7 }, (_, i) => {
      const d = addDays(start, i);
      const dateStr = format(d, 'yyyy-MM-dd');
      const activities = (report?.week_activities ?? []).filter(a => a.date === dateStr);
      return {
        date: dateStr,
        dayName: format(d, 'EEE'),
        dayNum: format(d, 'd'),
        isToday: dateStr === format(new Date(), 'yyyy-MM-dd'),
        activities,
      };
    });
  })();

  $: weightChange = (() => {
    if (weightData.length < 2) return null;
    return weightData[weightData.length - 1].weight - weightData[0].weight;
  })();

  onMount(async () => {
    try {
      const res = await fetch(`/api/report/${token}`);
      if (!res.ok) {
        if (res.status === 404) {
          error = 'This report link is no longer active.';
        } else {
          error = 'Failed to load report.';
        }
        return;
      }
      report = await res.json();
    } catch {
      error = 'Unable to connect. Please try again later.';
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>Health Report - Askesis</title>
  <meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <div class="max-w-2xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-8">
      <img src="/icon-192.png" alt="Askesis" class="w-10 h-10 rounded-xl" />
      <div>
        <h1 class="text-xl font-bold text-green-600">Askesis</h1>
        <p class="text-xs text-gray-400">Health Report</p>
      </div>
    </div>

    {#if loading}
      <div class="flex items-center justify-center py-20">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
      </div>
    {:else if error}
      <div class="text-center py-20">
        <p class="text-lg text-gray-500">{error}</p>
      </div>
    {:else if report}
      <!-- Date -->
      <p class="text-sm text-gray-400 mb-4">{format(parseISO(report.today), 'EEEE, MMMM d, yyyy')}</p>

      <!-- Latest Weight -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 mb-6 shadow-sm">
        <p class="text-sm text-gray-500 mb-1">Current Weight</p>
        <div class="flex items-baseline gap-2">
          <p class="text-4xl font-bold">
            {report.latest_weight?.toFixed(1) ?? '—'}
          </p>
          {#if report.latest_weight}
            <span class="text-lg text-gray-400">kg</span>
          {/if}
        </div>
        {#if report.latest_weight_date}
          <p class="text-xs text-gray-400 mt-1">
            as of {format(parseISO(report.latest_weight_date), 'MMM d, yyyy')}
          </p>
        {/if}
        {#if weightChange !== null}
          <p class="text-sm mt-2 {weightChange < 0 ? 'text-green-500' : weightChange > 0 ? 'text-red-500' : 'text-gray-400'}">
            {weightChange > 0 ? '+' : ''}{weightChange.toFixed(2)} kg over 30 days
          </p>
        {/if}
      </div>

      <!-- Weight Trend Chart -->
      {#if weightData.length > 1}
        <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 mb-6 shadow-sm">
          <h2 class="text-sm font-semibold text-gray-500 mb-4">Weight Trend (30 days)</h2>
          <div class="relative" style="aspect-ratio: 2/1;">
            <svg viewBox="0 0 {chartWidth} {chartHeight}" class="w-full h-full">
              <!-- Grid lines -->
              {#each yTicks as tick}
                <line
                  x1={padding.left}
                  y1={tick.y}
                  x2={chartWidth - padding.right}
                  y2={tick.y}
                  stroke="currentColor"
                  stroke-opacity="0.08"
                  stroke-dasharray="4,4"
                />
                <text
                  x={padding.left - 8}
                  y={tick.y}
                  text-anchor="end"
                  dominant-baseline="middle"
                  class="fill-gray-400 text-[10px]"
                >
                  {tick.value.toFixed(1)}
                </text>
              {/each}

              <!-- X-axis labels -->
              {#each weightData as point, i}
                {#if i === 0 || i === weightData.length - 1 || i === Math.floor(weightData.length / 2)}
                  <text
                    x={xScale(i)}
                    y={chartHeight - 5}
                    text-anchor="middle"
                    class="fill-gray-400 text-[10px]"
                  >
                    {format(parseISO(point.date), 'MMM d')}
                  </text>
                {/if}
              {/each}

              <!-- Trend line -->
              <path
                d={linePath}
                fill="none"
                stroke="#16a34a"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />

              <!-- Data points -->
              {#each weightData as point, i}
                <circle
                  cx={xScale(i)}
                  cy={yScale(point.weight)}
                  r="3"
                  fill="#16a34a"
                />
              {/each}
            </svg>
          </div>
        </div>
      {/if}

      <!-- This Week's Activities -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm">
        <h2 class="text-sm font-semibold text-gray-500 mb-4">
          This Week
          <span class="font-normal text-gray-400 ml-1">
            {format(parseISO(report.week_start), 'MMM d')} – {format(parseISO(report.week_end), 'MMM d')}
          </span>
        </h2>

        <div class="grid grid-cols-7 gap-2">
          {#each weekDays as day}
            <div class="text-center">
              <p class="text-xs text-gray-400 mb-1">{day.dayName}</p>
              <div
                class="rounded-xl p-2 min-h-[72px] flex flex-col items-center justify-start gap-1 transition-colors
                  {day.isToday ? 'bg-green-50 dark:bg-green-900/20 ring-2 ring-green-500/30' : 'bg-gray-50 dark:bg-gray-700/50'}"
              >
                <span class="text-sm font-semibold {day.isToday ? 'text-green-600' : 'text-gray-600 dark:text-gray-300'}">
                  {day.dayNum}
                </span>
                {#each day.activities as activity}
                  <span
                    class="w-full text-[9px] leading-tight text-center truncate px-0.5 py-0.5 rounded
                      {activity.activity_type === 'cardio' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' : 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300'}"
                    title="{activity.name}{activity.duration_mins ? ` — ${activity.duration_mins}min` : ''}"
                  >
                    {activity.name}
                  </span>
                {/each}
                {#if day.activities.length === 0}
                  <span class="text-gray-300 dark:text-gray-600 text-xs">—</span>
                {/if}
              </div>
            </div>
          {/each}
        </div>

        {#if report.week_activities.length > 0}
          <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
            <p class="text-xs text-gray-400">
              {report.week_activities.length} workout{report.week_activities.length === 1 ? '' : 's'} this week
              {#if report.week_activities.reduce((sum, a) => sum + (a.duration_mins || 0), 0) > 0}
                · {report.week_activities.reduce((sum, a) => sum + (a.duration_mins || 0), 0)} min total
              {/if}
            </p>
          </div>
        {/if}
      </div>

      <!-- Nutrition Averages -->
      {#if report.nutrition_avg && report.nutrition_avg.days_tracked > 0}
        <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 mb-6 shadow-sm">
          <h2 class="text-sm font-semibold text-gray-500 mb-4">
            Nutrition
            <span class="font-normal text-gray-400 ml-1">7-day average</span>
          </h2>
          <div class="grid grid-cols-4 gap-4">
            <div>
              <p class="text-xs text-gray-400">Calories</p>
              <p class="text-xl font-bold">{report.nutrition_avg.avg_calories ?? '—'}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400">Protein</p>
              <p class="text-xl font-bold">
                {report.nutrition_avg.avg_protein_g ?? '—'}{#if report.nutrition_avg.avg_protein_g}<span class="text-xs font-normal text-gray-400">g</span>{/if}
              </p>
            </div>
            <div>
              <p class="text-xs text-gray-400">Carbs</p>
              <p class="text-xl font-bold">
                {report.nutrition_avg.avg_carbs_g ?? '—'}{#if report.nutrition_avg.avg_carbs_g}<span class="text-xs font-normal text-gray-400">g</span>{/if}
              </p>
            </div>
            <div>
              <p class="text-xs text-gray-400">Fat</p>
              <p class="text-xl font-bold">
                {report.nutrition_avg.avg_fat_g ?? '—'}{#if report.nutrition_avg.avg_fat_g}<span class="text-xs font-normal text-gray-400">g</span>{/if}
              </p>
            </div>
          </div>
          <p class="text-xs text-gray-400 mt-3">Based on {report.nutrition_avg.days_tracked} day{report.nutrition_avg.days_tracked === 1 ? '' : 's'} tracked</p>
        </div>
      {/if}

      <!-- Body Measurements -->
      {#if report.latest_measurements}
        {@const m = report.latest_measurements}
        <div class="bg-white dark:bg-gray-800 rounded-2xl p-6 mb-6 shadow-sm">
          <h2 class="text-sm font-semibold text-gray-500 mb-4">
            Body Measurements
            <span class="font-normal text-gray-400 ml-1">{format(parseISO(m.date), 'MMM d, yyyy')}</span>
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
            {#each [
              ['Chest', m.chest],
              ['Waist', m.waist],
              ['Hips', m.hips],
              ['Shoulders', m.shoulders],
              ['Neck', m.neck],
              ['Abdomen', m.abdomen],
              ['Bicep L', m.bicep_left],
              ['Bicep R', m.bicep_right],
              ['Thigh L', m.thigh_left],
              ['Thigh R', m.thigh_right],
              ['Calf L', m.calf_left],
              ['Calf R', m.calf_right],
            ] as [label, value]}
              {#if value}
                <div class="flex justify-between items-baseline">
                  <span class="text-xs text-gray-400">{label}</span>
                  <span class="text-sm font-semibold">{Number(value).toFixed(1)} <span class="text-xs font-normal text-gray-400">cm</span></span>
                </div>
              {/if}
            {/each}
          </div>
        </div>
      {/if}

      <!-- Footer -->
      <p class="text-center text-xs text-gray-300 dark:text-gray-600 mt-8">
        Updated {format(parseISO(report.generated_at), 'MMM d, yyyy · h:mm a')}
      </p>
    {/if}
  </div>
</div>
