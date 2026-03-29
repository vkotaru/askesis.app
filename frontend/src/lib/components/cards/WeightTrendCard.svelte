<script lang="ts">
  import { format, subDays, subMonths } from 'date-fns';
  import { TrendingUp, TrendingDown } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { weightFromMetric, formatWeight, getWeightLabel } from '$lib/utils/units';
  import type { WeightUnit } from '$lib/api/client';

  export let weightPoints: { date: string; weight: number }[] = [];
  export let weightUnit: WeightUnit = 'kg';
  export let showRangeSelector: boolean = false;
  export let showMovingAverage: boolean = false;
  export let interactive: boolean = false;

  type TimeRange = '1w' | '2w' | '1m' | '6m' | 'all';
  let selectedRange: TimeRange = '1m';
  const TIME_RANGES: { value: TimeRange; label: string }[] = [
    { value: '1w', label: '1W' },
    { value: '2w', label: '2W' },
    { value: '1m', label: '1M' },
    { value: '6m', label: '6M' },
    { value: 'all', label: 'All' },
  ];

  let hoveredPoint: { x: number; y: number; weight: number; date: string } | null = null;

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

  $: rangeCutoff = showRangeSelector ? getRangeCutoff(selectedRange) : null;
  $: filteredData = weightPoints.filter(p => !rangeCutoff || new Date(p.date) >= rangeCutoff);

  $: weightChange = filteredData.length >= 2
    ? filteredData[filteredData.length - 1].weight - filteredData[0].weight
    : null;

  $: movingAvg = showMovingAverage ? filteredData.map((_, i) => {
    const start = Math.max(0, i - 6);
    const window = filteredData.slice(start, i + 1);
    return window.reduce((acc, p) => acc + p.weight, 0) / window.length;
  }) : [];

  const chartWidth = 400;
  const chartHeight = 200;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  $: weightMin = filteredData.length > 0 ? Math.min(...filteredData.map(p => p.weight)) - 1 : 0;
  $: weightMax = filteredData.length > 0 ? Math.max(...filteredData.map(p => p.weight)) + 1 : 100;
  $: weightRange = weightMax - weightMin || 1;

  $: xScale = (i: number) => padding.left + (i / Math.max(filteredData.length - 1, 1)) * innerWidth;
  $: yScale = (w: number) => padding.top + innerHeight - ((w - weightMin) / weightRange) * innerHeight;

  $: weightPath = filteredData.length > 1
    ? filteredData.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(p.weight)}`).join(' ')
    : '';

  $: maPath = movingAvg.length > 1
    ? movingAvg.map((avg, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(avg)}`).join(' ')
    : '';

  $: points = filteredData.map((p, i) => ({
    x: xScale(i),
    y: yScale(p.weight),
    weight: p.weight,
    date: p.date,
  }));

  $: yTicks = Array.from({ length: 5 }, (_, i) => ({
    value: weightMin + (weightRange * i) / 4,
    y: padding.top + innerHeight - (i / 4) * innerHeight,
  }));
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-4">
    <TrendingUp size={20} class="text-primary-500" />
    <h2 class="text-lg font-semibold">Weight Trend</h2>
    {#if showRangeSelector}
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
    {:else}
      <span class="text-xs text-gray-400 ml-auto">30 days</span>
    {/if}
  </div>

  {#if showRangeSelector && weightChange !== null}
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
        {weightChange > 0 ? '+' : ''}{weightFromMetric(weightChange, weightUnit).toFixed(2)} {getWeightLabel(weightUnit)}
      </span>
    </div>
  {/if}

  {#if filteredData.length > 0}
    <div class="relative" style="aspect-ratio: 2/1;">
      <svg
        viewBox="0 0 {chartWidth} {chartHeight}"
        class="w-full h-full"
        on:mouseleave={() => { if (interactive) hoveredPoint = null; }}
      >
        {#each yTicks as tick}
          <line x1={padding.left} y1={tick.y} x2={chartWidth - padding.right} y2={tick.y}
            stroke="currentColor" stroke-opacity="0.1" stroke-dasharray="4,4" />
          <text x={padding.left - 8} y={tick.y} text-anchor="end" dominant-baseline="middle"
            class="fill-gray-400 text-[10px]">
            {weightFromMetric(tick.value, weightUnit).toFixed(0)}
          </text>
        {/each}

        <text x={12} y={chartHeight / 2} text-anchor="middle" dominant-baseline="middle"
          transform="rotate(-90, 12, {chartHeight / 2})" class="fill-gray-400 text-[10px]">
          {getWeightLabel(weightUnit)}
        </text>

        {#if maPath}
          <path d={maPath} fill="none" stroke="currentColor" stroke-width="1.5"
            stroke-dasharray="4,4" class="text-orange-400" />
        {/if}

        {#if weightPath}
          <path d={weightPath} fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" class="text-primary-500" />
        {/if}

        {#each points as point}
          {@const dotRadius = points.length > 90 ? 1.5 : points.length > 30 ? 2.5 : 4}
          <circle
            cx={point.x} cy={point.y}
            r={hoveredPoint?.date === point.date ? dotRadius + 2 : dotRadius}
            class="fill-primary-500 {interactive ? 'cursor-pointer' : ''} transition-all"
            on:mouseenter={() => { if (interactive) hoveredPoint = point; }}
          />
        {/each}

        {#if filteredData.length > 0}
          <text x={padding.left} y={chartHeight - 8} text-anchor="start" class="fill-gray-400 text-[10px]">
            {format(new Date(filteredData[0].date), 'MMM d')}
          </text>
          {#if filteredData.length > 2}
            <text x={chartWidth / 2} y={chartHeight - 8} text-anchor="middle" class="fill-gray-400 text-[10px]">
              {format(new Date(filteredData[Math.floor(filteredData.length / 2)].date), 'MMM d')}
            </text>
          {/if}
          <text x={chartWidth - padding.right} y={chartHeight - 8} text-anchor="end" class="fill-gray-400 text-[10px]">
            {format(new Date(filteredData[filteredData.length - 1].date), 'MMM d')}
          </text>
        {/if}
      </svg>

      {#if interactive && hoveredPoint}
        <div
          class="absolute bg-gray-900 text-white text-xs px-2 py-1 rounded shadow-lg pointer-events-none z-10"
          style="left: {(hoveredPoint.x / chartWidth) * 100}%; top: {(hoveredPoint.y / chartHeight) * 100 - 15}%; transform: translateX(-50%);"
        >
          <div class="font-medium">{formatWeight(hoveredPoint.weight, weightUnit)}</div>
          <div class="text-gray-300">{format(new Date(hoveredPoint.date), 'MMM d, yyyy')}</div>
        </div>
      {/if}
    </div>

    {#if showMovingAverage}
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
    {/if}
  {:else}
    <div class="h-48 flex items-center justify-center text-gray-400">
      <p>No weight data yet. Start logging!</p>
    </div>
  {/if}
</div>
