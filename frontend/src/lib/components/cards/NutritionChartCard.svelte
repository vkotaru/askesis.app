<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { createEventDispatcher } from 'svelte';
  import { Flame } from 'lucide-svelte';

  export let data: { date: string; calories: number; protein: number; burnedCalories?: number }[] = [];
  export let subtitle: string = '';
  export let today: string = format(new Date(), 'yyyy-MM-dd');
  export let calorieTarget: number | null = null;
  export let proteinTarget: number | null = null;

  const dispatch = createEventDispatcher<{ dayClick: string }>();

  $: maxCalories = Math.max(...data.map(d => d.calories), (calorieTarget || 0) * 1.2, 1);
  $: maxProtein = Math.max(...data.map(d => d.protein) , (proteinTarget || 0) * 1.2, 1);
  $: hasBurned = data.some(d => (d.burnedCalories || 0) > 0);

  // Averages over the days that HAVE a figure, never over the calendar week.
  // `data` is always seven days long — one entry per date, zero where nothing was
  // logged — so dividing by `data.length` made a partly-logged week read as
  // starvation: two days totalling 4,400 reported as 631 cal/day. A day with no
  // meals is a gap in the record, not a day of fasting.
  $: calorieDays = data.filter((d) => d.calories > 0);
  $: avgCalories =
    calorieDays.length > 0
      ? Math.round(calorieDays.reduce((sum, d) => sum + d.calories, 0) / calorieDays.length)
      : 0;
  $: proteinDays = data.filter(d => d.protein > 0);
  $: avgProtein = proteinDays.length > 0
    ? Math.round(proteinDays.reduce((sum, d) => sum + d.protein, 0) / proteinDays.length)
    : 0;

  // The bars, and the space under them that the day label and the burn figure
  // occupy. `labelSpace` has to match what those two actually take (19px + 8px),
  // because the dashed reference lines are positioned from the bottom of the
  // container and have to line up with the bars, not with the labels: a target
  // line sitting 3px off the bar it is there to be compared against is exactly
  // the kind of thing that reads as a chart you cannot trust.
  const intakeHeight = 200; // px
  const labelSpace = 27; // px — day label (19) + burn slot (8)
</script>

<div class="card p-4 md:p-6">
  <div class="flex items-center gap-2 mb-1">
    <Flame size={20} class="text-nutrition-500" />
    <h2 class="text-lg font-semibold">Calories & Protein</h2>
    {#if subtitle}
      <span class="text-xs text-gray-400 ml-auto">{subtitle}</span>
    {/if}
  </div>
  <div class="flex items-center gap-4 mb-2 flex-wrap">
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-orange-400"></span> Calories
    </span>
    <span class="flex items-center gap-1 text-[10px] text-gray-400">
      <span class="inline-block w-2 h-2 rounded-sm bg-blue-400"></span> Protein
    </span>
    {#if hasBurned}
      <span class="flex items-center gap-1 text-[10px] text-gray-400">
        <span class="inline-block w-2 h-2 rounded-sm bg-red-400"></span> Burned (active)
      </span>
    {/if}
    {#if calorieTarget}
      <span class="flex items-center gap-1 text-[10px] text-gray-400">
        <span class="inline-block w-4 h-0 border-t-2 border-dashed border-amber-400"></span> Cal Target
      </span>
    {/if}
    {#if proteinTarget}
      <span class="flex items-center gap-1 text-[10px] text-gray-400">
        <span class="inline-block w-4 h-0 border-t-2 border-dashed border-blue-400"></span> Pro Target
      </span>
    {/if}
  </div>

  <!-- Average summary -->
  {#if avgCalories > 0 || avgProtein > 0}
    <div class="flex items-center gap-3 mb-3 text-[10px] text-gray-400 flex-wrap">
      {#if avgCalories > 0}
        <span>
          Avg: <span class="font-medium text-orange-400">{avgCalories}</span> cal/day
          <span class="text-gray-500">
            over {calorieDays.length} logged day{calorieDays.length === 1 ? '' : 's'}
          </span>
        </span>
      {/if}
      {#if avgProtein > 0}
        <span>
          Avg: <span class="font-medium text-blue-400">{avgProtein}g</span> protein/day
          {#if proteinDays.length !== calorieDays.length}
            <span class="text-gray-500">
              over {proteinDays.length} day{proteinDays.length === 1 ? '' : 's'}
            </span>
          {/if}
        </span>
      {/if}
      {#if calorieTarget}
        <span>Target: <span class="font-medium text-amber-400">{calorieTarget}</span> cal</span>
      {/if}
      {#if proteinTarget}
        <span>Target: <span class="font-medium text-blue-400">{proteinTarget}g</span> protein</span>
      {/if}
    </div>
  {/if}

  {#if data.length > 0}
    <div
      class="flex items-end gap-2 relative"
      style="height: {intakeHeight + labelSpace + 16}px;"
    >
      <!-- Calorie target line -->
      {#if calorieTarget && maxCalories > 0}
        {@const targetPct = (calorieTarget / maxCalories) * 100}
        <div
          class="absolute left-0 right-0 border-t-2 border-dashed border-amber-400/60 pointer-events-none z-10"
          style="bottom: {labelSpace + (targetPct / 100) * intakeHeight}px;"
        ></div>
      {/if}

      <!-- Protein target line -->
      {#if proteinTarget && maxProtein > 0}
        {@const proTargetPct = (proteinTarget / maxProtein) * 100}
        <div
          class="absolute left-0 right-0 border-t-2 border-dashed border-blue-400/60 pointer-events-none z-10"
          style="bottom: {labelSpace + (proTargetPct / 100) * intakeHeight}px;"
        ></div>
      {/if}

      <!-- Weekly calorie average line -->
      {#if avgCalories > 0 && maxCalories > 0}
        {@const avgPct = (avgCalories / maxCalories) * 100}
        <div
          class="absolute left-0 right-0 border-t-2 border-dashed border-orange-400/60 pointer-events-none z-10"
          style="bottom: {labelSpace + (avgPct / 100) * intakeHeight}px;"
        ></div>
      {/if}

      <!-- Weekly protein average line -->
      {#if avgProtein > 0 && maxProtein > 0}
        {@const avgProPct = (avgProtein / maxProtein) * 100}
        <div
          class="absolute left-0 right-0 border-t border-dotted border-blue-400/50 pointer-events-none z-10"
          style="bottom: {labelSpace + (avgProPct / 100) * intakeHeight}px;"
        ></div>
      {/if}

      {#each data as day}
        {@const burned = day.burnedCalories || 0}
        {@const effectiveBurned = Math.min(burned, day.calories)}
        {@const netCals = Math.max(day.calories - effectiveBurned, 0)}
        {@const netPct = maxCalories > 0 ? (netCals / maxCalories) * 100 : 0}
        {@const burnPct = maxCalories > 0 ? (effectiveBurned / maxCalories) * 100 : 0}
        {@const proPct = maxProtein > 0 ? (day.protein / maxProtein) * 100 : 0}
        {@const isToday = day.date === today}
        <button
          type="button"
          class="flex-1 min-w-[20px] flex flex-col items-center gap-0 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors cursor-pointer p-0"
          on:click={() => dispatch('dayClick', day.date)}
        >
          <!-- Values above bars -->
          <div class="flex gap-1 justify-center h-4">
            {#if day.calories > 0}
              <span class="text-[9px] text-orange-400 font-medium">{(day.calories / 1000).toFixed(1)}k</span>
            {/if}
            {#if day.protein > 0}
              <span class="text-[9px] text-blue-400 font-medium">{Math.round(day.protein)}g</span>
            {/if}
          </div>

          <!-- Stacked calorie bar + protein bar, side by side -->
          <div class="w-full flex items-end gap-0.5" style="height: {intakeHeight}px;">
            <!-- Calorie column: net (orange) stacked under burned (red) -->
            <div class="flex-1 h-full flex flex-col justify-end">
              {#if effectiveBurned > 0}
                <div
                  class="w-full rounded-t-sm {isToday ? 'bg-red-500' : 'bg-red-300 dark:bg-red-700'}"
                  style="height: {Math.max(burnPct, 2)}%;"
                  title="Burned: {burned} cal"
                ></div>
              {/if}
              <div
                class="w-full {effectiveBurned > 0 ? '' : 'rounded-t-sm'} {isToday ? 'bg-orange-500' : 'bg-orange-300 dark:bg-orange-700'}"
                style="height: {Math.max(netPct, day.calories && effectiveBurned === 0 ? 3 : 0)}%;"
              ></div>
            </div>
            <!-- Protein column -->
            <div
              class="flex-1 rounded-t-sm {isToday ? 'bg-blue-500' : 'bg-blue-300 dark:bg-blue-700'}"
              style="height: {Math.max(proPct, day.protein ? 3 : 0)}%;"
            ></div>
          </div>

          <!-- Day label -->
          <span class="text-[10px] mt-1 {isToday ? 'text-green-600 font-semibold' : 'text-gray-400'}">
            {format(parseISO(day.date), 'EEE')}
          </span>

          <!-- Burn value below the day label, in a slot that is always present.
               The row is bottom-aligned, so an element that appears on some days
               and not others changes where that column's bars start: the days
               with a burn figure sat a line higher than the days without, and
               the chart read as if two bars had been nudged out of line. -->
          <span class="text-[8px] text-red-400 -mt-0.5 h-2.5 leading-none">
            {#if burned > 0}−{burned}{/if}
          </span>
        </button>
      {/each}
    </div>
  {:else}
    <div class="h-36 flex items-center justify-center text-gray-400">
      <p>No nutrition data yet</p>
    </div>
  {/if}
</div>
