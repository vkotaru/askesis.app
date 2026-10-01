<script lang="ts">
  /**
   * One metric over months, as a line or as bars.
   *
   * Hand-rolled SVG with a viewBox, matching `WeightTrendCard` rather than
   * pulling a chart library into a page that needs two shapes. The viewBox is
   * what makes it responsive: the chart is drawn in a fixed coordinate space
   * and scaled by CSS, so nothing here has to know how wide the phone is.
   *
   * `level` (weight, sleep) draws a line, because the value between two points
   * is a real thing that was true. `amount` (steps, calories) draws bars,
   * because it is not — nobody ate anything "between" Tuesday and Thursday, and
   * a line through two meals implies a third.
   */
  import { clsx } from 'clsx';
  import type { Bucket, Granularity } from '$lib/trends';

  export let buckets: Bucket[] = [];
  export let shape: 'level' | 'amount' = 'level';
  export let granularity: Granularity = 'day';
  /** Canonical value -> what the reader sees. Units convert here, not upstream. */
  export let format: (value: number) => string;
  export let color = '#3d8b65';
  /** Drawn as a dashed rule when the metric has one. */
  export let target: number | null = null;
  export let targetLabel = 'target';

  // The viewBox is scaled to the container's width, which on a phone is about
  // 310px — a factor of ~0.55. So every size in here is in viewBox units and
  // reads smaller than its number: a `font-size: 10` axis label renders at
  // about five pixels, which is what the first version shipped. The sizes below
  // are chosen for how they come out, not how they read in the source.
  //
  // The height is NOT fixed in CSS either. With `height: 220px` on a box this
  // wide, `preserveAspectRatio` letterboxes the drawing into the middle and
  // leaves two bands of white space — the chart looked half the size of the
  // card it sat in. `h-auto` lets the aspect ratio below set the height.
  const W = 560;
  const H = 300;
  const PAD = { top: 18, right: 14, bottom: 40, left: 72 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  let active: number | null = null;

  // An amount chart is read against zero — a bar starting at 480 implies a
  // 480-step day was nothing. A level chart is not: nobody weighs zero, and
  // anchoring weight at 0 flattens a six-month trend into a straight line.
  $: values = buckets.map((b) => b.value);
  $: rawMax = values.length ? Math.max(...values, target ?? -Infinity) : 1;
  $: rawMin = values.length ? Math.min(...values) : 0;
  $: lo = shape === 'amount' ? 0 : rawMin - (rawMax - rawMin || 1) * 0.15;
  $: hi = rawMax + (rawMax - rawMin || 1) * 0.15;
  $: span = hi - lo || 1;

  $: x = (i: number) =>
    PAD.left + (buckets.length === 1 ? innerW / 2 : (i / (buckets.length - 1)) * innerW);
  $: y = (v: number) => PAD.top + innerH - ((v - lo) / span) * innerH;

  $: linePath = buckets.map((b, i) => `${i ? 'L' : 'M'}${x(i)},${y(b.value)}`).join(' ');
  $: barWidth = Math.max(1.5, Math.min(26, (innerW / Math.max(buckets.length, 1)) * 0.68));

  // Three gridlines. More is noise at this height; fewer leaves the eye with
  // nothing to measure against.
  $: ticks = [lo, lo + span / 2, hi];

  /**
   * Which labels fit along the bottom.
   *
   * Every label would overlap past about eight buckets, so this takes evenly
   * spaced ones and always keeps the last — the right-hand edge is "now", and a
   * chart whose final label is three weeks before its final bar misreads badly.
   */
  $: labelEvery = Math.max(1, Math.ceil(buckets.length / 6));
  $: showLabel = (i: number) => {
    const last = buckets.length - 1;
    if (i === last) return true;
    if (i % labelEvery !== 0) return false;
    // The last label is always kept, so a computed one landing right beside it
    // draws both on top of each other — "6 Jul    2788Sep". Leave room.
    return last - i >= labelEvery * 0.75;
  };

  function pick(event: MouseEvent | TouchEvent) {
    if (!buckets.length) return;
    const svg = event.currentTarget as SVGSVGElement;
    const box = svg.getBoundingClientRect();
    const clientX =
      'touches' in event ? (event.touches[0]?.clientX ?? 0) : (event as MouseEvent).clientX;
    // Back out of CSS pixels into the viewBox's coordinate space.
    const vx = ((clientX - box.left) / box.width) * W;
    const ratio = (vx - PAD.left) / innerW;
    const i = Math.round(ratio * (buckets.length - 1));
    active = Math.min(Math.max(i, 0), buckets.length - 1);
  }
</script>

{#if buckets.length === 0}
  <div class="h-44 flex items-center justify-center text-sm text-gray-400">
    Nothing logged in this range.
  </div>
{:else}
  <!-- The readout sits above the chart rather than floating over it: a tooltip
       under a thumb is a tooltip you cannot read. -->
  <div class="h-5 text-xs tabular-nums flex items-center gap-2">
    {#if active !== null && buckets[active]}
      <span class="font-semibold" style="color: {color}">{format(buckets[active].value)}</span>
      <span class="text-gray-400">
        {granularity === 'day'
          ? buckets[active].start
          : `${granularity === 'week' ? 'week of' : ''} ${buckets[active].start}`}
        {#if granularity !== 'day'}
          · {buckets[active].days} day{buckets[active].days === 1 ? '' : 's'}
        {/if}
      </span>
    {:else}
      <span class="text-gray-400">
        {#if granularity === 'day'}Tap the chart for a day{:else}Tap for a {granularity}'s average{/if}
      </span>
    {/if}
  </div>

  <svg
    viewBox="0 0 {W} {H}"
    class="w-full h-auto"
    style="touch-action: pan-y;"
    role="img"
    aria-label="{buckets.length} points, {format(Math.min(...values))} to {format(
      Math.max(...values)
    )}"
    on:mousemove={pick}
    on:mouseleave={() => (active = null)}
    on:touchstart|passive={pick}
    on:touchmove|passive={pick}
  >
    {#each ticks as t}
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={y(t)}
        y2={y(t)}
        stroke="currentColor"
        stroke-width="1"
        class="text-gray-200 dark:text-gray-700"
      />
      <text
        x={PAD.left - 10}
        y={y(t) + 6}
        text-anchor="end"
        class="fill-gray-400"
        style="font-size: 17px"
      >
        {format(t)}
      </text>
    {/each}

    {#if target != null}
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={y(target)}
        y2={y(target)}
        stroke="#ef4444"
        stroke-width="1.5"
        stroke-dasharray="5 4"
      />
      <text x={W - PAD.right} y={y(target) - 6} text-anchor="end" fill="#ef4444" style="font-size: 15px">
        {targetLabel}
      </text>
    {/if}

    {#if shape === 'amount'}
      {#each buckets as b, i (b.key)}
        <rect
          x={x(i) - barWidth / 2}
          y={y(b.value)}
          width={barWidth}
          height={Math.max(1, PAD.top + innerH - y(b.value))}
          rx={barWidth > 5 ? 2 : 0}
          fill={color}
          opacity={active === null || active === i ? 0.9 : 0.4}
        />
      {/each}
    {:else}
      <path d={linePath} fill="none" stroke={color} stroke-width="2.5" stroke-linejoin="round" />
      {#if buckets.length <= 60}
        {#each buckets as b, i (b.key)}
          <circle cx={x(i)} cy={y(b.value)} r={active === i ? 6 : 3} fill={color} />
        {/each}
      {/if}
    {/if}

    {#if active !== null}
      <line
        x1={x(active)}
        x2={x(active)}
        y1={PAD.top}
        y2={PAD.top + innerH}
        stroke={color}
        stroke-width="1"
        opacity="0.5"
      />
    {/if}

    {#each buckets as b, i (b.key)}
      {#if showLabel(i)}
        <text
          x={x(i)}
          y={H - 12}
          text-anchor={i === 0 ? 'start' : i === buckets.length - 1 ? 'end' : 'middle'}
          class={clsx('fill-gray-400')}
          style="font-size: 16px"
        >
          {b.label}
        </text>
      {/if}
    {/each}
  </svg>
{/if}
