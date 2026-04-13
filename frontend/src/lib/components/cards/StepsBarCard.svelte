<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { createEventDispatcher } from 'svelte';
  import { Footprints } from 'lucide-svelte';

  export let steps: { date: string; steps: number | null }[] = [];
  export let today: string = format(new Date(), 'yyyy-MM-dd');
  export let subtitle: string = 'last 7 days';

  const dispatch = createEventDispatcher<{ dayClick: string }>();

  $: maxSteps = Math.max(...steps.map(s => s.steps ?? 0), 1);

  $: daysWithSteps = steps.filter(s => (s.steps ?? 0) > 0);
  $: avgSteps = daysWithSteps.length > 0
    ? Math.round(daysWithSteps.reduce((sum, s) => sum + (s.steps ?? 0), 0) / daysWithSteps.length)
    : 0;
  $: avgPct = maxSteps > 0 ? (avgSteps / maxSteps) * 100 : 0;
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-1">
    <Footprints size={20} class="text-cardio-500" />
    <h2 class="text-lg font-semibold">Steps</h2>
    <span class="text-xs text-gray-400 ml-auto">{subtitle}</span>
  </div>
  {#if avgSteps > 0}
    <div class="flex items-center gap-2 mb-3 text-[10px] text-gray-400">
      <span class="inline-block w-4 h-0 border-t-2 border-dashed border-green-400"></span>
      <span>Avg: <span class="font-medium text-green-500">{(avgSteps / 1000).toFixed(1)}k</span>/day</span>
    </div>
  {/if}
  <div class="flex items-end gap-2 relative" style="height: 240px;">
    <!-- Average line -->
    {#if avgSteps > 0}
      <div
        class="absolute left-0 right-0 border-t-2 border-dashed border-green-400/60 pointer-events-none z-10"
        style="bottom: {(avgPct / 100) * 200 + 24}px;"
      ></div>
    {/if}

    {#each steps as day}
      {@const pct = day.steps ? (day.steps / maxSteps) * 100 : 0}
      {@const isToday = day.date === today}
      <button
        type="button"
        class="flex-1 flex flex-col items-center gap-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors cursor-pointer p-0"
        on:click={() => dispatch('dayClick', day.date)}
      >
        {#if day.steps}
          <span class="text-[9px] text-gray-400 font-medium">{(day.steps / 1000).toFixed(1)}k</span>
        {/if}
        <div class="w-full flex items-end" style="height: 200px;">
          <div
            class="w-full rounded-t-md transition-all {isToday ? 'bg-green-500' : 'bg-green-300 dark:bg-green-700'}"
            style="height: {Math.max(pct, day.steps ? 4 : 0)}%;"
          ></div>
        </div>
        <span class="text-[10px] {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
          {format(parseISO(day.date), 'EEE')}
        </span>
      </button>
    {/each}
  </div>
</div>
