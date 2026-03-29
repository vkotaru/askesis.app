<script lang="ts">
  import { format, parseISO } from 'date-fns';

  export let steps: { date: string; steps: number | null }[] = [];
  export let today: string = format(new Date(), 'yyyy-MM-dd');

  $: maxSteps = Math.max(...steps.map(s => s.steps ?? 0), 1);
</script>

<div class="card p-6">
  <h2 class="text-sm font-semibold text-gray-500 mb-4">Steps <span class="font-normal text-gray-400 ml-1">last 7 days</span></h2>
  <div class="flex items-end gap-2 h-32">
    {#each steps as day}
      {@const pct = day.steps ? (day.steps / maxSteps) * 100 : 0}
      {@const isToday = day.date === today}
      <div class="flex-1 flex flex-col items-center gap-1">
        {#if day.steps}
          <span class="text-[9px] text-gray-400 font-medium">{(day.steps / 1000).toFixed(1)}k</span>
        {/if}
        <div class="w-full flex items-end" style="height: 96px;">
          <div
            class="w-full rounded-t-md transition-all {isToday ? 'bg-green-500' : 'bg-green-300 dark:bg-green-700'}"
            style="height: {Math.max(pct, day.steps ? 4 : 0)}%;"
          ></div>
        </div>
        <span class="text-[10px] {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
          {format(parseISO(day.date), 'EEE')}
        </span>
      </div>
    {/each}
  </div>
</div>
