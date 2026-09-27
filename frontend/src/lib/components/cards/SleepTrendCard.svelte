<script lang="ts">
  /**
   * Sleep over time: a bar per night, with the 7-night average drawn over them
   * as a line.
   *
   * Each of the two encodes what it is good at, which a single mark cannot do.
   * A night's sleep is a measured quantity, and a bar is how you compare
   * quantities — you can see at a glance which nights were short. The average is
   * not a measurement of anything; it is a trend, and a line is how a trend
   * reads. Drawing the nights as a line (the first version of this card) made
   * every night look like a point on a continuous signal, which sleep is not:
   * the gaps between bars are where nights are missing, and a line closes them
   * silently.
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

  // Zero-based, because these are bars now. A window fitted to the data (the
  // previous 4..10) makes a 6.2-hour night a stub beside a 6.4-hour one, which
  // is a lie about proportion that a line chart gets away with and a bar chart
  // does not: the height of a bar has to mean the hours in it.
  const yMin = 0;
  $: yMax = Math.max(10, target ?? 0, ...data.map((p) => Math.ceil(p.hours) + 1));
  $: span = yMax - yMin || 1;

  // One slot per night, and x is the CENTRE of that slot — a bar is drawn from
  // the slot's edges, and the average line has to pass through bar centres or it
  // will not line up with the thing it averages.
  $: slot = innerW / Math.max(data.length, 1);
  $: x = (i: number) => pad.left + slot * (i + 0.5);
  $: y = (h: number) => pad.top + innerH - ((h - yMin) / span) * innerH;
  // Wide bars with a hairline gap, narrowing as the range grows; never thinner
  // than a pixel, or a long range renders as an empty grid.
  $: barW = Math.max(1, Math.min(slot - 2, 28));

  $: avgPath =
    rolling.length > 1
      ? rolling.map((h, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(h)}`).join(' ')
      : '';

  $: bars = data.map((p, i) => ({
    x: x(i) - barW / 2,
    y: y(p.hours),
    h: Math.max(pad.top + innerH - y(p.hours), 1),
    hours: p.hours,
    date: p.date,
    centre: x(i),
  }));

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

        {#each bars as bar}
          <rect
            x={bar.x}
            y={bar.y}
            width={barW}
            height={bar.h}
            rx={Math.min(2, barW / 2)}
            class={clsx(
              'cursor-pointer transition-all',
              hovered?.date === bar.date ? 'fill-strength-600' : 'fill-strength-400'
            )}
            role="presentation"
            on:mouseenter={() =>
              (hovered = { x: bar.centre, y: bar.y, hours: bar.hours, date: bar.date })}
          />
        {/each}

        <!-- After the bars, not before: SVG paints in document order and has no
             z-index, so drawn first the average would sit behind them. -->
        {#if avgPath}
          <path
            d={avgPath}
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="text-orange-500"
          />
        {/if}

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
        <div class="w-2 h-3 bg-strength-400 rounded-sm"></div>
        <span>Per night</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-0.5 bg-orange-500 rounded"></div>
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
