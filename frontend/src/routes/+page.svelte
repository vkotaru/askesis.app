<script lang="ts">
  import { onMount } from 'svelte';
  import { format, subDays, subMonths } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets, Activity, TrendingUp, TrendingDown } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type DailyLog, type Activity as ActivityType } from '$lib/api/client';
  import { settings } from '$lib/stores/settings';
  import { formatWeight, weightFromMetric, formatWater, formatDistance, getWeightLabel } from '$lib/utils/units';

  let logs: DailyLog[] = [];
  let activities: ActivityType[] = [];
  let loading = true;
  let hoveredPoint: { x: number; y: number; weight: number; date: string } | null = null;

  // Weight trend time range
  type TimeRange = '1w' | '2w' | '1m' | '6m' | 'all';
  let selectedRange: TimeRange = '1m';
  const TIME_RANGES: { value: TimeRange; label: string }[] = [
    { value: '1w', label: '1W' },
    { value: '2w', label: '2W' },
    { value: '1m', label: '1M' },
    { value: '6m', label: '6M' },
    { value: 'all', label: 'All' },
  ];

  const today = format(new Date(), 'yyyy-MM-dd');

  onMount(async () => {
    try {
      // Fetch data - use higher limit for weight chart
      [logs, activities] = await Promise.all([
        api.getDailyLogs(undefined, undefined, undefined, 365),
        api.getActivities(undefined, undefined, undefined, 10),
      ]);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      loading = false;
    }
  });

  // Get cutoff date for selected range
  function getRangeCutoff(range: TimeRange): Date | null {
    const now = new Date();
    switch (range) {
      case '1w': return subDays(now, 7);
      case '2w': return subDays(now, 14);
      case '1m': return subMonths(now, 1);
      case '6m': return subMonths(now, 6);
      case 'all': return null;
    }
  }

  // Get most recent log for each metric (logs are sorted newest first from API)
  $: latestWeightLog = logs.find((l) => l.weight);
  $: latestSleepLog = logs.find((l) => l.sleep_hours);
  $: latestStepsLog = logs.find((l) => l.steps);
  $: latestWaterLog = logs.find((l) => l.water_ml);

  // Filter and sort weight data based on selected range
  $: rangeCutoff = getRangeCutoff(selectedRange);
  $: weightData = logs
    .filter((l) => l.weight && (!rangeCutoff || new Date(l.date) >= rangeCutoff))
    .reverse();

  // Calculate weight change (first to last)
  $: weightChange = weightData.length >= 2
    ? (weightData[weightData.length - 1].weight || 0) - (weightData[0].weight || 0)
    : null;

  // Calculate 7-day moving average
  $: movingAverage = weightData.map((_, i) => {
    const start = Math.max(0, i - 6);
    const window = weightData.slice(start, i + 1);
    const sum = window.reduce((acc, l) => acc + (l.weight || 0), 0);
    return sum / window.length;
  });

  // Chart dimensions
  const chartWidth = 400;
  const chartHeight = 200;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  // Calculate scales
  $: weightMin = weightData.length > 0 ? Math.min(...weightData.map(l => l.weight || 0)) - 1 : 0;
  $: weightMax = weightData.length > 0 ? Math.max(...weightData.map(l => l.weight || 0)) + 1 : 100;
  $: weightRange = weightMax - weightMin || 1;

  // Generate path for weight line
  $: weightPath = weightData.length > 1
    ? weightData.map((log, i) => {
        const x = padding.left + (i / (weightData.length - 1)) * innerWidth;
        const y = padding.top + innerHeight - ((log.weight || 0) - weightMin) / weightRange * innerHeight;
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ')
    : '';

  // Generate path for moving average
  $: maPath = movingAverage.length > 1
    ? movingAverage.map((avg, i) => {
        const x = padding.left + (i / (movingAverage.length - 1)) * innerWidth;
        const y = padding.top + innerHeight - (avg - weightMin) / weightRange * innerHeight;
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ')
    : '';

  // Generate point coordinates
  $: points = weightData.map((log, i) => ({
    x: padding.left + (weightData.length > 1 ? (i / (weightData.length - 1)) * innerWidth : innerWidth / 2),
    y: padding.top + innerHeight - ((log.weight || 0) - weightMin) / weightRange * innerHeight,
    weight: log.weight || 0,
    date: log.date,
  }));

  // Y-axis ticks
  $: yTicks = Array.from({ length: 5 }, (_, i) => {
    const value = weightMin + (weightRange * i) / 4;
    return {
      value: Math.round(value * 10) / 10,
      y: padding.top + innerHeight - (i / 4) * innerHeight,
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
    <!-- Today's snapshot -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Weight</p>
            <p class="text-2xl font-bold">
              {latestWeightLog?.weight ? weightFromMetric(latestWeightLog.weight, $settings.weight_unit).toFixed(1) : '—'}
              {#if latestWeightLog?.weight}
                <span class="text-sm font-normal text-gray-400 ml-1">{getWeightLabel($settings.weight_unit)}</span>
              {/if}
            </p>
            {#if latestWeightLog && latestWeightLog.date !== today}
              <p class="text-xs text-gray-400 mt-1">{format(new Date(latestWeightLog.date), 'MMM d')}</p>
            {/if}
          </div>
          <div class="p-2 rounded-lg bg-rest-100 dark:bg-rest-900/30">
            <Scale size={20} class="text-rest-500" />
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Sleep</p>
            <p class="text-2xl font-bold">
              {latestSleepLog?.sleep_hours ?? '—'}
              {#if latestSleepLog?.sleep_hours}
                <span class="text-sm font-normal text-gray-400 ml-1">hrs</span>
              {/if}
            </p>
            {#if latestSleepLog && latestSleepLog.date !== today}
              <p class="text-xs text-gray-400 mt-1">{format(new Date(latestSleepLog.date), 'MMM d')}</p>
            {/if}
          </div>
          <div class="p-2 rounded-lg bg-strength-100 dark:bg-strength-900/30">
            <Moon size={20} class="text-strength-500" />
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Steps</p>
            <p class="text-2xl font-bold">{latestStepsLog?.steps ?? '—'}</p>
            {#if latestStepsLog && latestStepsLog.date !== today}
              <p class="text-xs text-gray-400 mt-1">{format(new Date(latestStepsLog.date), 'MMM d')}</p>
            {/if}
          </div>
          <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
            <Footprints size={20} class="text-cardio-500" />
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Water</p>
            <p class="text-2xl font-bold">
              {formatWater(latestWaterLog?.water_ml, $settings.water_unit)}
            </p>
            {#if latestWaterLog && latestWaterLog.date !== today}
              <p class="text-xs text-gray-400 mt-1">{format(new Date(latestWaterLog.date), 'MMM d')}</p>
            {/if}
          </div>
          <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
            <Droplets size={20} class="text-cardio-400" />
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Weight trend line chart -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-4">
          <TrendingUp size={20} class="text-primary-500" />
          <h2 class="text-lg font-semibold">Weight Trend</h2>
          <div class="flex items-center gap-1 ml-auto">
            {#each TIME_RANGES as { value, label }}
              <button
                on:click={() => selectedRange = value}
                class={clsx(
                  'px-2 py-1 text-xs rounded-md font-medium transition-colors',
                  selectedRange === value
                    ? 'bg-primary-500 text-white'
                    : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
                )}
              >
                {label}
              </button>
            {/each}
          </div>
        </div>

        {#if weightChange !== null}
          <div class="flex items-center gap-2 mb-4 text-sm">
            <span class="text-gray-500">Change:</span>
            <span class={clsx(
              'flex items-center gap-1 font-medium',
              weightChange < 0 ? 'text-green-500' : weightChange > 0 ? 'text-red-500' : 'text-gray-500'
            )}>
              {#if weightChange < 0}
                <TrendingDown size={16} />
              {:else if weightChange > 0}
                <TrendingUp size={16} />
              {/if}
              {weightChange > 0 ? '+' : ''}{weightFromMetric(weightChange, $settings.weight_unit).toFixed(1)} {getWeightLabel($settings.weight_unit)}
            </span>
          </div>
        {/if}

        {#if weightData.length > 0}
          <div class="relative" style="aspect-ratio: 2/1;">
            <svg
              viewBox="0 0 {chartWidth} {chartHeight}"
              class="w-full h-full"
              on:mouseleave={() => hoveredPoint = null}
            >
              <!-- Grid lines -->
              {#each yTicks as tick}
                <line
                  x1={padding.left}
                  y1={tick.y}
                  x2={chartWidth - padding.right}
                  y2={tick.y}
                  stroke="currentColor"
                  stroke-opacity="0.1"
                  stroke-dasharray="4,4"
                />
                <text
                  x={padding.left - 8}
                  y={tick.y}
                  text-anchor="end"
                  dominant-baseline="middle"
                  class="fill-gray-400 text-[10px]"
                >
                  {weightFromMetric(tick.value, $settings.weight_unit).toFixed(0)}
                </text>
              {/each}

              <!-- Y-axis label -->
              <text
                x={12}
                y={chartHeight / 2}
                text-anchor="middle"
                dominant-baseline="middle"
                transform="rotate(-90, 12, {chartHeight / 2})"
                class="fill-gray-400 text-[10px]"
              >
                {getWeightLabel($settings.weight_unit)}
              </text>

              <!-- Moving average line (dashed) -->
              {#if maPath}
                <path
                  d={maPath}
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-dasharray="4,4"
                  class="text-orange-400"
                />
              {/if}

              <!-- Weight line -->
              {#if weightPath}
                <path
                  d={weightPath}
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class="text-primary-500"
                />
              {/if}

              <!-- Data points -->
              {#each points as point, i}
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={hoveredPoint?.date === point.date ? 6 : 4}
                  class="fill-primary-500 cursor-pointer transition-all"
                  on:mouseenter={() => hoveredPoint = point}
                />
              {/each}

              <!-- X-axis labels (show first, middle, last) -->
              {#if weightData.length > 0}
                <text
                  x={padding.left}
                  y={chartHeight - 8}
                  text-anchor="start"
                  class="fill-gray-400 text-[10px]"
                >
                  {format(new Date(weightData[0].date), 'MMM d')}
                </text>
                {#if weightData.length > 2}
                  <text
                    x={chartWidth / 2}
                    y={chartHeight - 8}
                    text-anchor="middle"
                    class="fill-gray-400 text-[10px]"
                  >
                    {format(new Date(weightData[Math.floor(weightData.length / 2)].date), 'MMM d')}
                  </text>
                {/if}
                <text
                  x={chartWidth - padding.right}
                  y={chartHeight - 8}
                  text-anchor="end"
                  class="fill-gray-400 text-[10px]"
                >
                  {format(new Date(weightData[weightData.length - 1].date), 'MMM d')}
                </text>
              {/if}
            </svg>

            <!-- Tooltip -->
            {#if hoveredPoint}
              <div
                class="absolute bg-gray-900 text-white text-xs px-2 py-1 rounded shadow-lg pointer-events-none z-10"
                style="left: {(hoveredPoint.x / chartWidth) * 100}%; top: {(hoveredPoint.y / chartHeight) * 100 - 15}%; transform: translateX(-50%);"
              >
                <div class="font-medium">{formatWeight(hoveredPoint.weight, $settings.weight_unit)}</div>
                <div class="text-gray-300">{format(new Date(hoveredPoint.date), 'MMM d, yyyy')}</div>
              </div>
            {/if}
          </div>

          <!-- Legend -->
          <div class="flex items-center justify-center gap-6 mt-4 text-xs text-gray-500">
            <div class="flex items-center gap-2">
              <div class="w-4 h-0.5 bg-primary-500 rounded"></div>
              <span>Weight</span>
            </div>
            <div class="flex items-center gap-2">
              <div class="w-4 h-0.5 bg-orange-400 rounded" style="border-top: 2px dashed;"></div>
              <span>7-day avg</span>
            </div>
          </div>
        {:else}
          <div class="h-48 flex items-center justify-center text-gray-400">
            <p>No weight data yet. Start logging!</p>
          </div>
        {/if}
      </div>

      <!-- Recent activities -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-4">
          <Activity size={20} class="text-cardio-500" />
          <h2 class="text-lg font-semibold">Recent Activities</h2>
        </div>
        {#if activities.length > 0}
          <ul class="space-y-3">
            {#each activities.slice(0, 5) as activity}
              <li class="flex items-center justify-between py-3 px-4 rounded-lg bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                <div>
                  <p class="font-medium">{activity.name}</p>
                  <p class="text-sm text-gray-500">
                    {format(new Date(activity.date), 'MMM d')}
                    {#if activity.duration_mins} · {activity.duration_mins} min{/if}
                    {#if activity.distance_km} · {activity.distance_km} km{/if}
                  </p>
                </div>
                <span
                  class={clsx(
                    'text-xs px-3 py-1 rounded-full font-medium',
                    activity.activity_type === 'cardio'
                      ? 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400'
                      : 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400'
                  )}
                >
                  {activity.activity_type}
                </span>
              </li>
            {/each}
          </ul>
        {:else}
          <div class="h-48 flex items-center justify-center text-gray-400">
            <p>No activities yet. Let's get moving!</p>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
