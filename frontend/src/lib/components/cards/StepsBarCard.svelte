<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { createEventDispatcher } from 'svelte';
  import { Footprints, Bike } from 'lucide-svelte';

  export let steps: { date: string; steps: number | null; bikeSteps?: number }[] = [];
  export let today: string = format(new Date(), 'yyyy-MM-dd');
  export let subtitle: string = 'last 7 days';

  const dispatch = createEventDispatcher<{ dayClick: string }>();

  // Each bar is walked steps plus the walking-equivalent of that day's cycling
  // (see lib/utils/stepEquivalent.ts — energy equivalence from the 2011
  // Compendium, not a flat per-minute rate). The scale has to be driven by the
  // COMBINED total, or a day with a long ride overflows the plot area.
  $: rows = steps.map(d => {
    const walked = d.steps ?? 0;
    const biked = d.bikeSteps ?? 0;
    return { ...d, walked, biked, total: walked + biked };
  });

  $: maxTotal = Math.max(...rows.map(r => r.total), 1);
  $: anyBike = rows.some(r => r.biked > 0);

  // Averaged over days that recorded SOMETHING. A day with no step data is a
  // gap in the record rather than a zero, and including it would quietly drag
  // the average down every time a watch went unworn.
  $: active = rows.filter(r => r.total > 0);
  $: avgTotal =
    active.length > 0 ? Math.round(active.reduce((sum, r) => sum + r.total, 0) / active.length) : 0;
  $: avgPct = maxTotal > 0 ? (avgTotal / maxTotal) * 100 : 0;

  // Same two numbers the nutrition chart names, and for the same reason: the
  // dashed average line is positioned from the bottom of the container, so it
  // has to clear exactly what sits under the bars (the gap plus the day label)
  // or it floats off the bars it is drawn to be compared against.
  const barHeight = 200; // px
  const labelSpace = 19; // px — gap (4) + day label (15)

  const k = (n: number) => `${(n / 1000).toFixed(1)}k`;
</script>

<div class="card p-4 md:p-6">
  <div class="flex items-center gap-2 mb-1">
    <Footprints size={20} class="text-cardio-500" />
    <h2 class="text-lg font-semibold">Steps</h2>
    <span class="text-xs text-gray-400 ml-auto">{subtitle}</span>
  </div>

  <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[10px] text-gray-400">
    {#if avgTotal > 0}
      <span class="flex items-center gap-1">
        <span class="inline-block w-4 h-0 border-t-2 border-dashed border-green-400"></span>
        Avg <span class="font-medium text-green-500">{k(avgTotal)}</span>/day
      </span>
    {/if}
    {#if anyBike}
      <span class="flex items-center gap-1">
        <span class="inline-block w-2 h-2 rounded-sm bg-green-400"></span> walked
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-2 h-2 rounded-sm bg-sky-400"></span>
        <Bike size={10} class="text-sky-400" /> bike equivalent
      </span>
    {/if}
  </div>

  <div
    class="flex items-end gap-2 relative"
    style="height: {barHeight + labelSpace + 21}px;"
  >
    {#if avgTotal > 0}
      <div
        class="absolute left-0 right-0 border-t-2 border-dashed border-green-400/60 pointer-events-none z-10"
        style="bottom: {labelSpace + (avgPct / 100) * barHeight}px;"
      ></div>
    {/if}

    {#each rows as day}
      {@const walkPct = (day.walked / maxTotal) * 100}
      {@const bikePct = (day.biked / maxTotal) * 100}
      {@const isToday = day.date === today}
      <button
        type="button"
        class="flex-1 flex flex-col items-center gap-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors cursor-pointer p-0"
        on:click={() => dispatch('dayClick', day.date)}
        title={day.biked > 0
          ? `${day.walked.toLocaleString()} walked + ${day.biked.toLocaleString()} bike equivalent`
          : `${day.walked.toLocaleString()} steps`}
      >
        {#if day.total > 0}
          <span class="text-[9px] text-gray-400 font-medium">{k(day.total)}</span>
        {/if}

        <!-- Stacked, bike on top: the walked figure is the measured one, so it
             keeps the baseline and stays comparable across days regardless of
             whether that day had a ride. -->
        <div class="w-full flex flex-col justify-end" style="height: {barHeight}px;">
          {#if day.biked > 0}
            <div
              class="w-full rounded-t-md transition-all {isToday
                ? 'bg-sky-500'
                : 'bg-sky-300 dark:bg-sky-700'}"
              style="height: {Math.max(bikePct, 2)}%;"
            ></div>
          {/if}
          {#if day.walked > 0}
            <div
              class="w-full transition-all {day.biked > 0 ? '' : 'rounded-t-md'} {isToday
                ? 'bg-green-500'
                : 'bg-green-300 dark:bg-green-700'}"
              style="height: {Math.max(walkPct, 2)}%;"
            ></div>
          {/if}
        </div>

        <span class="text-[10px] {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
          {format(parseISO(day.date), 'EEE')}
        </span>
      </button>
    {/each}
  </div>
</div>
