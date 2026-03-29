<script lang="ts">
  import { format, parseISO } from 'date-fns';

  export let nutrition: { date: string; calories: number; protein_g: number }[] = [];
  export let today: string = format(new Date(), 'yyyy-MM-dd');

  $: maxCalories = Math.max(...nutrition.map(n => n.calories), 1);
  $: maxProtein = Math.max(...nutrition.map(n => n.protein_g), 1);
</script>

<div class="card p-6">
  <h2 class="text-sm font-semibold text-gray-500 mb-1">Nutrition <span class="font-normal text-gray-400 ml-1">last 7 days</span></h2>
  <div class="flex items-center gap-4 mb-4">
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-orange-400"></span> Calories (kcal)
    </span>
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-blue-400"></span> Protein (grams)
    </span>
  </div>
  <div class="flex items-end gap-2 h-36">
    {#each nutrition as day}
      {@const calPct = maxCalories > 0 ? (day.calories / maxCalories) * 100 : 0}
      {@const proPct = maxProtein > 0 ? (day.protein_g / maxProtein) * 100 : 0}
      {@const isToday = day.date === today}
      <div class="flex-1 flex flex-col items-center gap-1">
        <div class="flex gap-1 justify-center">
          {#if day.calories > 0}
            <span class="text-[9px] text-orange-400 font-medium">{(day.calories / 1000).toFixed(1)}k</span>
          {/if}
          {#if day.protein_g > 0}
            <span class="text-[9px] text-blue-400 font-medium">{Math.round(day.protein_g)}g</span>
          {/if}
        </div>
        <div class="w-full flex items-end gap-0.5" style="height: 104px;">
          <div
            class="flex-1 rounded-t-sm {isToday ? 'bg-orange-500' : 'bg-orange-300 dark:bg-orange-700'}"
            style="height: {Math.max(calPct, day.calories ? 3 : 0)}%;"
          ></div>
          <div
            class="flex-1 rounded-t-sm {isToday ? 'bg-blue-500' : 'bg-blue-300 dark:bg-blue-700'}"
            style="height: {Math.max(proPct, day.protein_g ? 3 : 0)}%;"
          ></div>
        </div>
        <span class="text-[10px] {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
          {format(parseISO(day.date), 'EEE')}
        </span>
      </div>
    {/each}
  </div>
</div>
