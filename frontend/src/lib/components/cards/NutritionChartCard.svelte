<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { Flame } from 'lucide-svelte';

  export let data: { date: string; calories: number; protein: number }[] = [];
  export let subtitle: string = '';
  export let today: string = format(new Date(), 'yyyy-MM-dd');

  $: maxCalories = Math.max(...data.map(d => d.calories), 1);
  $: maxProtein = Math.max(...data.map(d => d.protein), 1);

  // Show day abbreviation for <= 14 days, otherwise date
  $: useDayLabel = data.length <= 14;
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-1">
    <Flame size={20} class="text-nutrition-500" />
    <h2 class="text-lg font-semibold">Calories & Protein</h2>
    {#if subtitle}
      <span class="text-xs text-gray-400 ml-auto">{subtitle}</span>
    {/if}
  </div>
  <div class="flex items-center gap-4 mb-4">
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-orange-400"></span> Calories (kcal)
    </span>
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-blue-400"></span> Protein (grams)
    </span>
  </div>
  {#if data.length > 0}
    <div class="flex items-end gap-{data.length > 14 ? '0.5' : '2'} h-36 overflow-x-auto">
      {#each data as day}
        {@const calPct = maxCalories > 0 ? (day.calories / maxCalories) * 100 : 0}
        {@const proPct = maxProtein > 0 ? (day.protein / maxProtein) * 100 : 0}
        {@const isToday = day.date === today}
        <div class="flex-1 min-w-[20px] flex flex-col items-center gap-1">
          {#if data.length <= 14}
            <div class="flex gap-1 justify-center">
              {#if day.calories > 0}
                <span class="text-[9px] text-orange-400 font-medium">{(day.calories / 1000).toFixed(1)}k</span>
              {/if}
              {#if day.protein > 0}
                <span class="text-[9px] text-blue-400 font-medium">{Math.round(day.protein)}g</span>
              {/if}
            </div>
          {/if}
          <div class="w-full flex items-end gap-0.5" style="height: 104px;">
            <div
              class="flex-1 rounded-t-sm {isToday ? 'bg-orange-500' : 'bg-orange-300 dark:bg-orange-700'}"
              style="height: {Math.max(calPct, day.calories ? 3 : 0)}%;"
            ></div>
            <div
              class="flex-1 rounded-t-sm {isToday ? 'bg-blue-500' : 'bg-blue-300 dark:bg-blue-700'}"
              style="height: {Math.max(proPct, day.protein ? 3 : 0)}%;"
            ></div>
          </div>
          {#if useDayLabel}
            <span class="text-[10px] {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
              {format(parseISO(day.date), 'EEE')}
            </span>
          {:else if data.indexOf(day) === 0 || data.indexOf(day) === data.length - 1}
            <span class="text-[9px] text-gray-400">
              {format(parseISO(day.date), 'M/d')}
            </span>
          {/if}
        </div>
      {/each}
    </div>
  {:else}
    <div class="h-36 flex items-center justify-center text-gray-400">
      <p>No nutrition data yet</p>
    </div>
  {/if}
</div>
