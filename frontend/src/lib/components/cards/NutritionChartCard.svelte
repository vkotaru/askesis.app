<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { Flame } from 'lucide-svelte';

  export let data: { date: string; calories: number; protein: number; burnedCalories?: number }[] = [];
  export let subtitle: string = '';
  export let today: string = format(new Date(), 'yyyy-MM-dd');
  export let calorieTarget: number | null = null;

  $: maxCalories = Math.max(...data.map(d => d.calories), calorieTarget || 0, 1);
  $: maxProtein = Math.max(...data.map(d => d.protein), 1);
  $: maxBurned = Math.max(...data.map(d => d.burnedCalories || 0), 0);
  $: hasBurned = data.some(d => (d.burnedCalories || 0) > 0);

  // Weekly average calories
  $: avgCalories = data.length > 0
    ? Math.round(data.reduce((sum, d) => sum + d.calories, 0) / data.length)
    : 0;

  // Scale: top portion for intake bars, bottom portion for burn bars
  // burn section is proportional to max burn vs max calories
  $: burnRatio = hasBurned && maxBurned > 0 ? Math.min(maxBurned / maxCalories, 0.4) : 0;
  $: intakeHeight = 200; // px
  $: burnHeight = hasBurned ? Math.round(intakeHeight * burnRatio) : 0;
  $: totalBarHeight = intakeHeight + burnHeight;
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-1">
    <Flame size={20} class="text-nutrition-500" />
    <h2 class="text-lg font-semibold">Calories & Protein</h2>
    {#if subtitle}
      <span class="text-xs text-gray-400 ml-auto">{subtitle}</span>
    {/if}
  </div>
  <div class="flex items-center gap-4 mb-2">
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-orange-400"></span> Calories
    </span>
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-blue-400"></span> Protein
    </span>
    {#if hasBurned}
      <span class="flex items-center gap-1 text-[10px] text-gray-400">
        <span class="inline-block w-2 h-2 rounded-sm bg-red-400"></span> Burned
      </span>
    {/if}
    {#if calorieTarget}
      <span class="flex items-center gap-1 text-[10px] text-gray-400">
        <span class="inline-block w-4 h-0 border-t-2 border-dashed border-amber-400"></span> Target
      </span>
    {/if}
  </div>

  <!-- Average summary -->
  {#if avgCalories > 0}
    <div class="flex items-center gap-3 mb-3 text-[10px] text-gray-400">
      <span>Avg: <span class="font-medium text-orange-400">{avgCalories}</span> cal/day</span>
      {#if calorieTarget}
        <span>Target: <span class="font-medium text-amber-400">{calorieTarget}</span></span>
      {/if}
    </div>
  {/if}

  {#if data.length > 0}
    <div class="flex items-end gap-2 relative" style="height: {totalBarHeight + 40}px;">
      <!-- Calorie target line -->
      {#if calorieTarget && maxCalories > 0}
        {@const targetPct = (calorieTarget / maxCalories) * 100}
        <div
          class="absolute left-0 right-0 border-t-2 border-dashed border-amber-400/60 pointer-events-none z-10"
          style="bottom: {burnHeight + 24 + (targetPct / 100) * intakeHeight}px;"
        ></div>
      {/if}

      <!-- Weekly average line -->
      {#if avgCalories > 0 && maxCalories > 0}
        {@const avgPct = (avgCalories / maxCalories) * 100}
        <div
          class="absolute left-0 right-0 border-t-2 border-dashed border-orange-400/60 pointer-events-none z-10"
          style="bottom: {burnHeight + 24 + (avgPct / 100) * intakeHeight}px;"
        ></div>
      {/if}

      {#each data as day}
        {@const calPct = maxCalories > 0 ? (day.calories / maxCalories) * 100 : 0}
        {@const proPct = maxProtein > 0 ? (day.protein / maxProtein) * 100 : 0}
        {@const burnPct = maxBurned > 0 ? ((day.burnedCalories || 0) / maxBurned) * 100 : 0}
        {@const isToday = day.date === today}
        <div class="flex-1 min-w-[20px] flex flex-col items-center gap-0">
          <!-- Values above bars -->
          <div class="flex gap-1 justify-center h-4">
            {#if day.calories > 0}
              <span class="text-[9px] text-orange-400 font-medium">{(day.calories / 1000).toFixed(1)}k</span>
            {/if}
            {#if day.protein > 0}
              <span class="text-[9px] text-blue-400 font-medium">{Math.round(day.protein)}g</span>
            {/if}
          </div>

          <!-- Intake bars (positive axis) -->
          <div class="w-full flex items-end gap-0.5" style="height: {intakeHeight}px;">
            <div
              class="flex-1 rounded-t-sm {isToday ? 'bg-orange-500' : 'bg-orange-300 dark:bg-orange-700'}"
              style="height: {Math.max(calPct, day.calories ? 3 : 0)}%;"
            ></div>
            <div
              class="flex-1 rounded-t-sm {isToday ? 'bg-blue-500' : 'bg-blue-300 dark:bg-blue-700'}"
              style="height: {Math.max(proPct, day.protein ? 3 : 0)}%;"
            ></div>
          </div>

          <!-- Burn bars (negative axis, below baseline, aligned under calories only) -->
          {#if hasBurned}
            <div class="w-full flex items-start gap-0.5" style="height: {burnHeight}px;">
              <div
                class="flex-1 rounded-b-sm {(day.burnedCalories || 0) > 0 ? (isToday ? 'bg-red-500' : 'bg-red-300 dark:bg-red-700') : ''}"
                style="height: {(day.burnedCalories || 0) > 0 ? Math.max(burnPct, 3) + '%' : '0'};"
              ></div>
              <div class="flex-1"></div>
            </div>
          {/if}

          <!-- Day label -->
          <span class="text-[10px] mt-1 {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
            {format(parseISO(day.date), 'EEE')}
          </span>

          <!-- Burn value below day label -->
          {#if (day.burnedCalories || 0) > 0}
            <span class="text-[8px] text-red-400 -mt-0.5">{day.burnedCalories}</span>
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
