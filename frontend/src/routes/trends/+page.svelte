<script lang="ts">
  /**
   * The long view: one metric, months at a time.
   *
   * The dashboard answers "how is this week going" and should keep doing only
   * that. This answers "what have the last six months looked like", which is a
   * different question with different needs — you pick a metric, you pick a
   * range, and anything past a few months is rolled up because a year of daily
   * bars is a pixel each on a phone.
   *
   * **Entirely local.** The app already hydrates up to 500 days of logs and
   * nutrition into IndexedDB and never evicts them, so this page needs no new
   * endpoint and works with the plane in flight mode. The one consequence worth
   * knowing is the cap: past about sixteen months of daily logs the oldest rows
   * are simply not on the device, and the page says so rather than drawing a
   * history that quietly begins where the cache does.
   *
   * The aggregation rules live in `$lib/trends` so they are one implementation
   * rather than one per metric — in particular "average over the days that have
   * a figure, never over the calendar", which is the rule that stops a week
   * with two logged days reading as a fifth of what was actually eaten.
   */
  import { onMount } from 'svelte';
  import { clsx } from 'clsx';
  import { TrendingUp, TrendingDown, Minus } from 'lucide-svelte';
  import { offlineApi } from '$lib/stores/data';
  import { settings } from '$lib/stores/settings';
  import { dataVersion } from '$lib/stores/data';
  import { partVisible } from '$lib/appMode';
  import {
    RANGES,
    bucket,
    coverage,
    granularityFor,
    summarise,
    withinRange,
    type DayPoint,
    type RangeKey,
  } from '$lib/trends';
  import TrendChart from '$lib/components/TrendChart.svelte';
  import {
    weightFromMetric,
    getWeightLabel,
    distanceFromMetric,
    getDistanceLabel,
  } from '$lib/utils/units';

  interface MetricDef {
    key: string;
    label: string;
    /** See TrendChart: a level is a line, an amount is bars. */
    shape: 'level' | 'amount';
    color: string;
    /** Canonical value -> display string, including the unit. */
    format: (v: number) => string;
    /** Shorter, for the summary row where three sit side by side. */
    short: (v: number) => string;
    /** From settings, drawn as a dashed rule. */
    target?: number | null;
    /**
     * Whether a direction is good. Left undefined on purpose for most metrics:
     * more calories is better on a bulk and worse on a cut, and the app does
     * not know which you are doing. An unopinionated arrow is grey.
     */
    lowerIsBetter?: boolean;
    /** Hidden on a gym-only account. */
    part?: string;
  }

  let points: Record<string, DayPoint[]> = {};
  let loading = true;
  let error = '';
  let selected = 'weight';
  let range: RangeKey = '6m';
  let seen = -1;
  /** How many days the cache actually holds, so the page can be honest about it. */
  let oldest: string | null = null;

  $: wUnit = $settings.weight_unit;
  $: dUnit = $settings.distance_unit;

  const n0 = (v: number) => Math.round(v).toLocaleString();
  const n1 = (v: number) => (Math.round(v * 10) / 10).toLocaleString();

  $: METRICS = [
    {
      key: 'weight',
      label: 'Weight',
      shape: 'level',
      color: '#3d8b65',
      format: (v: number) => `${n1(weightFromMetric(v, wUnit))} ${getWeightLabel(wUnit)}`,
      short: (v: number) => n1(weightFromMetric(v, wUnit)),
      // Deliberately no opinion: this app is used by someone cutting and by
      // someone who is not, and colouring a gain red would be the app taking a
      // side it has no business taking.
    },
    {
      key: 'sleep',
      label: 'Sleep',
      shape: 'level',
      color: '#6366f1',
      format: (v: number) => `${n1(v)} h`,
      short: (v: number) => `${n1(v)} h`,
      lowerIsBetter: false,
    },
    {
      key: 'steps',
      label: 'Steps',
      shape: 'amount',
      color: '#0ea5e9',
      format: n0,
      short: n0,
      target: $settings.step_target ?? null,
      lowerIsBetter: false,
    },
    {
      key: 'calories',
      label: 'Calories',
      shape: 'amount',
      color: '#fb923c',
      format: (v: number) => `${n0(v)} cal`,
      short: n0,
      target: $settings.calorie_target ?? null,
      part: 'trendsNutrition',
    },
    {
      key: 'protein',
      label: 'Protein',
      shape: 'amount',
      color: '#a855f7',
      format: (v: number) => `${n0(v)} g`,
      short: (v: number) => `${n0(v)} g`,
      target: $settings.protein_target ?? null,
      part: 'trendsNutrition',
    },
    {
      key: 'training',
      label: 'Training',
      shape: 'amount',
      color: '#f43f5e',
      format: (v: number) => `${n0(v)} min`,
      short: (v: number) => `${n0(v)} min`,
    },
    {
      key: 'distance',
      label: 'Distance',
      shape: 'amount',
      color: '#14b8a6',
      format: (v: number) => `${n1(distanceFromMetric(v, dUnit))} ${getDistanceLabel(dUnit)}`,
      short: (v: number) => n1(distanceFromMetric(v, dUnit)),
      part: 'trendsNutrition',
    },
  ] satisfies MetricDef[] as MetricDef[];

  $: visibleMetrics = METRICS.filter(
    (m) => !m.part || partVisible($settings.app_mode, m.part)
  );
  // A mode change can hide whatever was selected, which would leave the page
  // drawing a chart with no chip lit.
  $: if (visibleMetrics.length && !visibleMetrics.some((m) => m.key === selected)) {
    selected = visibleMetrics[0].key;
  }

  $: metric = visibleMetrics.find((m) => m.key === selected) ?? visibleMetrics[0];
  $: series = points[selected] ?? [];
  $: inRange = withinRange(series, range);
  $: granularity = granularityFor(inRange);
  $: buckets = bucket(inRange, granularity);
  $: stats = summarise(inRange);
  $: windowDays = coverage(inRange, range);

  /**
   * Pull every metric once, from the cache.
   *
   * One pass rather than per-metric fetches: switching chips should be instant,
   * and these are four reads of tables that are already in memory. A day with
   * no figure for a metric contributes no point to it — never a zero, which
   * would drag every average toward the floor and draw a line through a gap as
   * though someone had weighed nothing.
   */
  async function load() {
    try {
      const [logs, nutrition, meals, activities] = await Promise.all([
        offlineApi.getDailyLogs(undefined, undefined, undefined, 500),
        offlineApi.getNutritionHistory(undefined, undefined, undefined, 500),
        offlineApi.getMeals(undefined, undefined, undefined, undefined, 2000),
        offlineApi.getActivities(undefined, undefined, undefined, 500),
      ]);

      const num = (rows: { date: string }[], pick: (r: never) => number | null | undefined) =>
        rows
          .map((r) => ({ date: r.date, value: pick(r as never) }))
          .filter((p): p is DayPoint => p.value != null && isFinite(p.value as number))
          .sort((a, b) => a.date.localeCompare(b.date));

      // Calories and training come from rows that are one-per-event, not
      // one-per-day, so they are summed into days first.
      const sumByDate = (
        rows: { date: string }[],
        pick: (r: never) => number | null | undefined
      ): DayPoint[] => {
        const totals = new Map<string, number>();
        for (const r of rows) {
          const v = pick(r as never);
          if (v == null || !isFinite(v)) continue;
          totals.set(r.date, (totals.get(r.date) ?? 0) + v);
        }
        return [...totals.entries()]
          .filter(([, v]) => v > 0)
          .map(([date, value]) => ({ date, value }))
          .sort((a, b) => a.date.localeCompare(b.date));
      };

      points = {
        weight: num(logs, (r: { weight?: number | null }) => r.weight),
        sleep: num(logs, (r: { sleep_hours?: number | null }) => r.sleep_hours),
        steps: num(logs, (r: { steps?: number | null }) => r.steps),
        protein: num(nutrition, (r: { protein_g?: number | null }) => r.protein_g),
        calories: sumByDate(meals, (m: { calories?: number | null }) => m.calories),
        training: sumByDate(activities, (a: { duration_mins?: number | null }) => a.duration_mins),
        distance: sumByDate(activities, (a: { distance_km?: number | null }) => a.distance_km),
      };

      const earliest = Object.values(points)
        .flat()
        .map((p) => p.date)
        .sort();
      oldest = earliest[0] ?? null;
      error = '';
    } catch {
      error = 'Could not read your history.';
    } finally {
      loading = false;
    }
  }

  onMount(load);
  // Re-read when a sync actually changed something, like every other page.
  $: if ($dataVersion !== seen) {
    seen = $dataVersion;
    void load();
  }

  $: direction = stats?.change == null ? 0 : Math.sign(stats.change);
  $: opinion = metric?.lowerIsBetter === undefined ? 0 : metric.lowerIsBetter ? -1 : 1;
</script>

<svelte:head><title>Trends · Askesis</title></svelte:head>

<div class="space-y-4">
  <div>
    <h1 class="text-2xl font-bold">Trends</h1>
    <p class="text-sm text-gray-500">Everything you've logged, as far back as it goes.</p>
  </div>

  {#if error}
    <p class="text-sm text-red-500">{error}</p>
  {/if}

  <!-- Metric first, then range: you choose what you are looking at before you
       choose how far back, and a chip row scrolls horizontally rather than
       wrapping into three rows on a phone. -->
  <div class="flex gap-1.5 overflow-x-auto scrollbar-hide -mx-3 px-3 pb-1">
    {#each visibleMetrics as m (m.key)}
      <button
        type="button"
        on:click={() => (selected = m.key)}
        class={clsx(
          'px-3 py-1.5 rounded-full text-sm whitespace-nowrap border transition-colors',
          selected === m.key
            ? 'text-white border-transparent font-medium'
            : 'border-gray-200 dark:border-gray-600 text-gray-500'
        )}
        style={selected === m.key ? `background:${m.color}` : ''}
      >
        {m.label}
      </button>
    {/each}
  </div>

  <div class="card p-4 space-y-3">
    <div class="flex items-center gap-2">
      <h2 class="font-semibold flex-1 min-w-0 truncate">{metric?.label}</h2>
      <div class="flex gap-0.5">
        {#each RANGES as r (r.value)}
          <button
            type="button"
            on:click={() => (range = r.value)}
            class={clsx(
              'px-2 py-1 text-xs rounded transition-colors',
              range === r.value
                ? 'bg-gray-100 dark:bg-gray-700 font-medium'
                : 'text-gray-400 hover:text-gray-600'
            )}
          >
            {r.label}
          </button>
        {/each}
      </div>
    </div>

    {#if loading}
      <div class="h-44 flex items-center justify-center text-sm text-gray-400">Reading…</div>
    {:else if metric}
      {#if stats}
        <!-- Average, range and the direction of travel. `logged` is beside them
             on purpose: "7.1 h average" means a different thing over 142 nights
             than over 9, and that denominator is the first thing to doubt. -->
        <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm tabular-nums">
          <span>
            <span class="text-gray-400 text-xs">avg</span>
            <b class="ml-1">{metric.format(stats.average)}</b>
          </span>
          <span class="text-gray-500">
            <span class="text-gray-400 text-xs">range</span>
            {metric.short(stats.min)}–{metric.short(stats.max)}
          </span>
          {#if stats.change != null && direction !== 0}
            <span
              class={clsx(
                'flex items-center gap-0.5',
                opinion === 0
                  ? 'text-gray-500'
                  : direction === opinion
                    ? 'text-primary-600'
                    : 'text-accent-600'
              )}
            >
              {#if direction > 0}<TrendingUp size={14} />{:else}<TrendingDown size={14} />{/if}
              {metric.short(Math.abs(stats.change))}
            </span>
          {:else if stats.change != null}
            <span class="flex items-center gap-0.5 text-gray-400"><Minus size={14} /> flat</span>
          {/if}
          <span class="text-gray-400 text-xs ml-auto">
            <!-- `{#if}` eats the whitespace around it, so the space before
                 "of" has to be explicit or this reads "149of 184". -->
            {stats.logged}{#if windowDays}&nbsp;of {windowDays}{/if} days
          </span>
        </div>
      {/if}

      <TrendChart
        {buckets}
        {granularity}
        shape={metric.shape}
        color={metric.color}
        format={metric.short}
        target={metric.target ?? null}
      />

      {#if granularity !== 'day' && buckets.length}
        <p class="text-[11px] text-gray-400">
          Each point is one {granularity}'s average over the days you logged.
        </p>
      {/if}
    {/if}
  </div>

  {#if oldest}
    <!-- Said rather than implied. The device holds the last 500 days; beyond
         that "All" is the cache's horizon, not yours, and a chart that starts
         abruptly with no explanation looks like lost data. -->
    <p class="text-[11px] text-gray-400 px-1">
      This device holds your history back to {oldest}. Older entries are on the
      server and are not charted here.
    </p>
  {/if}
</div>
