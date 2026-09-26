<script lang="ts">
  /**
   * Sleep over time, as a line with a 7-night average behind it.
   *
   * Deliberately shaped like `WeightTrendCard` rather than like the steps bars:
   * sleep is a level you drift around, not a daily total you accumulate, and the
   * question is which way the level is moving. The rolling average is the part
   * that answers it — a single bad night says nothing.
   *
   * Nights with no figure are **gaps, not zeros**. They are dropped from the
   * line rather than plotted at the bottom, and left out of every average: a
   * night the watch went uncharged is missing data, and drawing it as "no sleep"
   * would make an unworn watch look like insomnia.
   */
  import { format, subDays, subMonths, parseISO } from 'date-fns';
  import { Moon, TrendingUp, TrendingDown } from 'lucide-svelte';
  import { clsx } from 'clsx';

  export let sleepPoints: { date: string; hours: number }[] = [];
  /** Hours per night the user is aiming for, drawn as a reference line. */
  export let target: number | null = null;

  type TimeRange = '1w' | '2w' | '1m' | '6m' | 'all';
  let selectedRange: TimeRange = '1m';
  const TIME_RANGES: { value: TimeRange; label: string }[] = [
    { value: '1w', label: '1W' },
    { value: '2w', label: '2W' },
    { value: '1m', label: '1M' },
    { value: '6m', label: '6M' },
    { value: 'all', label: 'All' },
  ];

  let hovered: { x: number; y: number; hours: number; date: string } | null = null;

  function rangeCutoff(range: TimeRange): Date | null {
    const now = new Date();
    switch (range) {
      case '1w':
        return subDays(now, 7);
      case '2w':
        return subDays(now, 14);
      case '1m':
        return subMonths(now, 1);
      case '6m':
        return subMonths(now, 6);
      case 'all':
        return null;
    }
  }

  $: cutoff = rangeCutoff(selectedRange);
  $: data = sleepPoints
    .filter((p) => p.hours > 0 && (!cutoff || parseISO(p.date) >= cutoff))
    .sort((a, b) => a.date.localeCompare(b.date));

  $: avg = data.length > 0 ? data.reduce((s, p) => s + p.hours, 0) / data.length : 0;

  // Compared like for like: the first and last thirds of the range, not the
  // first and last night. Two single nights would make noise look like a trend.
  $: change = (() => {
    if (data.length < 4) return null;
    const size = Math.max(2, Math.floor(data.length / 3));
    const mean = (xs: typeof data) => xs.reduce((s, p) => s + p.hours, 0) / xs.length;
    return mean(data.slice(-size)) - mean(data.slice(0, size));
  })();

  $: rolling = data.map((_, i) => {
    const window = data.slice(Math.max(0, i - 6), i + 1);
    return window.reduce((s, p) => s + p.hours, 0) / window.length;
  });

  const width = 400;
  const height = 200;
  const pad = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  // Anchored to a plausible range of a night's sleep rather than to the data, so
  // the line does not swing wildly on a quiet week — but widened when a reading
  // falls outside it.
  $: yMin = Math.min(4, ...data.map((p) => Math.floor(p.hours) - 1));
  $: yMax = Math.max(10, target ?? 0, ...data.map((p) => Math.ceil(p.hours) + 1));
  $: span = yMax - yMin || 1;

  $: x = (i: number) => pad.left + (i / Math.max(data.length - 1, 1)) * innerW;
  $: y = (h: number) => pad.top + innerH - ((h - yMin) / span) * innerH;

  $: linePath =
    data.length > 1
      ? data.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(p.hours)}`).join(' ')
      : '';
  $: avgPath =
    rolling.length > 1
      ? rolling.map((h, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(h)}`).join(' ')
      : '';

  $: points = data.map((p, i) => ({ x: x(i), y: y(p.hours), hours: p.hours, date: p.date }));

  $: ticks = Array.from({ length: 5 }, (_, i) => ({
    value: yMin + (span * i) / 4,
    y: pad.top + innerH - (i / 4) * innerH,
  }));

  const hrs = (h: number) => `${h.toFixed(1)} hrs`;
</script>

<div class="card p-4 md:p-6">
  <div class="flex items-center gap-2 mb-2">
    <Moon size={20} class="text-strength-500" />
    <h2 class="text-lg font-semibold">Sleep Trend</h2>
    <div class="flex items-center gap-1 ml-auto">
      {#each TIME_RANGES as { value, label }}
        <button
          type="button"
          on:click={() => (selectedRange = value)}
          class={clsx(
            'px-2 py-1 text-xs rounded-md font-medium transition-colors',
            selectedRange === value
              ? 'bg-strength-500 text-white'
              : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
          )}
        >
          {label}
        </button>
      {/each}
    </div>
  </div>

  {#if data.length > 0}
    <div class="flex items-center gap-4 mb-4 text-sm flex-wrap">
      <span class="text-gray-500">
        Avg <span class="font-medium text-strength-500">{hrs(avg)}</span>
        <span class="text-xs text-gray-400">
          over {data.length} night{data.length === 1 ? '' : 's'}
        </span>
      </span>
      {#if change !== null}
        <span
          class={clsx(
            'flex items-center gap-1 font-medium',
            change > 0.2 ? 'text-green-500' : change < -0.2 ? 'text-red-500' : 'text-gray-500'
          )}
        >
          {#if change > 0.2}
            <TrendingUp size={16} />
          {:else if change < -0.2}
            <TrendingDown size={16} />
          {/if}
          {change > 0 ? '+' : ''}{change.toFixed(1)} hrs
        </span>
      {/if}
    </div>

    <div class="relative" style="aspect-ratio: 2/1;">
      <svg
        viewBox="0 0 {width} {height}"
        class="w-full h-full"
        on:mouseleave={() => (hovered = null)}
        role="img"
        aria-label="Sleep hours per night over the selected range"
      >
        {#each ticks as tick}
          <line
            x1={pad.left}
            y1={tick.y}
            x2={width - pad.right}
            y2={tick.y}
            stroke="currentColor"
            stroke-opacity="0.1"
            stroke-dasharray="4,4"
          />
          <text
            x={pad.left - 8}
            y={tick.y}
            text-anchor="end"
            dominant-baseline="middle"
            class="fill-gray-400 text-[10px]"
          >
            {tick.value.toFixed(0)}
          </text>
        {/each}

        <text
          x={12}
          y={height / 2}
          text-anchor="middle"
          dominant-baseline="middle"
          transform="rotate(-90, 12, {height / 2})"
          class="fill-gray-400 text-[10px]"
        >
          hrs
        </text>

        {#if target}
          <line
            x1={pad.left}
            y1={y(target)}
            x2={width - pad.right}
            y2={y(target)}
            stroke="currentColor"
            stroke-width="1.5"
            stroke-dasharray="5,3"
            class="text-amber-400/70"
          />
        {/if}

        {#if avgPath}
          <path
            d={avgPath}
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-dasharray="4,4"
            class="text-orange-400"
          />
        {/if}

        {#if linePath}
          <path
            d={linePath}
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="text-strength-500"
          />
        {/if}

        {#each points as point}
          {@const r = points.length > 90 ? 1.5 : points.length > 30 ? 2.5 : 4}
          <circle
            cx={point.x}
            cy={point.y}
            r={hovered?.date === point.date ? r + 2 : r}
            class="fill-strength-500 cursor-pointer transition-all"
            role="presentation"
            on:mouseenter={() => (hovered = point)}
          />
        {/each}

        <text x={pad.left} y={height - 8} text-anchor="start" class="fill-gray-400 text-[10px]">
          {format(parseISO(data[0].date), 'MMM d')}
        </text>
        {#if data.length > 2}
          <text x={width / 2} y={height - 8} text-anchor="middle" class="fill-gray-400 text-[10px]">
            {format(parseISO(data[Math.floor(data.length / 2)].date), 'MMM d')}
          </text>
        {/if}
        <text
          x={width - pad.right}
          y={height - 8}
          text-anchor="end"
          class="fill-gray-400 text-[10px]"
        >
          {format(parseISO(data[data.length - 1].date), 'MMM d')}
        </text>
      </svg>

      {#if hovered}
        <div
          class="absolute bg-gray-900 text-white text-xs px-2 py-1 rounded shadow-lg pointer-events-none z-10"
          style="left: {(hovered.x / width) * 100}%; top: {(hovered.y / height) * 100 -
            15}%; transform: translateX(-50%);"
        >
          <div class="font-medium">{hrs(hovered.hours)}</div>
          <div class="text-gray-300">{format(parseISO(hovered.date), 'MMM d, yyyy')}</div>
        </div>
      {/if}
    </div>

    <div class="flex items-center justify-center gap-6 mt-4 text-xs text-gray-500 flex-wrap">
      <div class="flex items-center gap-2">
        <div class="w-4 h-0.5 bg-strength-500 rounded"></div>
        <span>Per night</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-0.5 bg-orange-400 rounded" style="border-top: 2px dashed;"></div>
        <span>7-night avg</span>
      </div>
      {#if target}
        <div class="flex items-center gap-2">
          <div class="w-4 h-0.5 bg-amber-400 rounded" style="border-top: 2px dashed;"></div>
          <span>Target</span>
        </div>
      {/if}
    </div>
  {:else}
    <div class="h-48 flex items-center justify-center text-gray-400 text-center px-4">
      <p>
        {sleepPoints.length > 0
          ? 'No sleep logged in this range.'
          : 'No sleep data yet. Log a night, or sync Garmin.'}
      </p>
    </div>
  {/if}
</div>
