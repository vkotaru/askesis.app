<script lang="ts">
  import { Dumbbell, Bike, PersonStanding } from 'lucide-svelte';

  export let weeklyData: { label: string; bikeMiles: number; roadMiles: number; strengthCount: number }[] = [];
  export let distanceLabel: string = 'mi';

  const chartWidth = 400;
  const chartHeight = 200;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  $: maxBikeMiles = Math.max(...weeklyData.map(w => w.bikeMiles), 1);
  $: maxRoadMiles = Math.max(...weeklyData.map(w => w.roadMiles), 1);
  $: maxStrength = Math.max(...weeklyData.map(w => w.strengthCount), 1);
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-4">
    <Dumbbell size={20} class="text-strength-500" />
    <h2 class="text-lg font-semibold">Weekly Training</h2>
    <span class="text-xs text-gray-400 ml-auto">Last 8 weeks</span>
  </div>
  {#if weeklyData.some(w => w.bikeMiles > 0 || w.roadMiles > 0 || w.strengthCount > 0)}
    <div class="relative" style="aspect-ratio: 2/1;">
      <svg viewBox="0 0 {chartWidth} {chartHeight}" class="w-full h-full">
        {#each [0, 0.25, 0.5, 0.75, 1] as tick}
          <line x1={padding.left} y1={padding.top + innerHeight * (1 - tick)}
            x2={chartWidth - padding.right} y2={padding.top + innerHeight * (1 - tick)}
            stroke="currentColor" stroke-opacity="0.1" stroke-dasharray="4,4" />
        {/each}

        {#each weeklyData as week, i}
          {@const groupWidth = innerWidth / weeklyData.length}
          {@const barWidth = groupWidth * 0.25}
          {@const groupX = padding.left + i * groupWidth + groupWidth * 0.1}

          {@const bikeHeight = (week.bikeMiles / maxBikeMiles) * innerHeight}
          <rect x={groupX} y={padding.top + innerHeight - bikeHeight} width={barWidth} height={bikeHeight}
            class="fill-cardio-400" rx="2" />

          {@const roadHeight = (week.roadMiles / maxRoadMiles) * innerHeight}
          <rect x={groupX + barWidth + 2} y={padding.top + innerHeight - roadHeight} width={barWidth} height={roadHeight}
            class="fill-rest-400" rx="2" />

          {@const strengthHeight = (week.strengthCount / maxStrength) * innerHeight}
          <rect x={groupX + (barWidth + 2) * 2} y={padding.top + innerHeight - strengthHeight} width={barWidth} height={strengthHeight}
            class="fill-strength-400" rx="2" />

          <text x={groupX + groupWidth * 0.35} y={chartHeight - 8} text-anchor="middle" class="fill-gray-400 text-[8px]">
            {week.label}
          </text>
        {/each}

        <text x={padding.left - 8} y={padding.top} text-anchor="end" dominant-baseline="middle" class="fill-cardio-500 text-[9px] font-medium">{Math.round(maxBikeMiles)}</text>
        <text x={padding.left - 8} y={padding.top + innerHeight / 2} text-anchor="end" dominant-baseline="middle" class="fill-cardio-500 text-[9px]">{Math.round(maxBikeMiles / 2)}</text>
        <text x={padding.left - 8} y={padding.top + innerHeight} text-anchor="end" dominant-baseline="middle" class="fill-cardio-500 text-[9px]">0</text>

        <text x={chartWidth - padding.right + 8} y={padding.top} text-anchor="start" dominant-baseline="middle" class="fill-rest-500 text-[9px] font-medium">{Math.round(maxRoadMiles)}</text>
        <text x={chartWidth - padding.right + 8} y={padding.top + innerHeight / 2} text-anchor="start" dominant-baseline="middle" class="fill-rest-500 text-[9px]">{Math.round(maxRoadMiles / 2)}</text>
        <text x={chartWidth - padding.right + 8} y={padding.top + innerHeight} text-anchor="start" dominant-baseline="middle" class="fill-rest-500 text-[9px]">0</text>
      </svg>
    </div>

    <div class="flex items-center justify-center gap-4 mt-4 text-xs text-gray-500">
      <div class="flex items-center gap-1"><Bike size={12} class="text-cardio-400" /><span>Bike (left)</span></div>
      <div class="flex items-center gap-1"><PersonStanding size={12} class="text-rest-400" /><span>Run (right)</span></div>
      <div class="flex items-center gap-1"><Dumbbell size={12} class="text-strength-400" /><span>Strength</span></div>
    </div>

    <div class="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
      <div class="text-center">
        <p class="text-lg font-bold text-cardio-500">{weeklyData.reduce((sum, w) => sum + w.bikeMiles, 0).toFixed(0)}</p>
        <p class="text-xs text-gray-400">Total bike {distanceLabel}</p>
      </div>
      <div class="text-center">
        <p class="text-lg font-bold text-rest-500">{weeklyData.reduce((sum, w) => sum + w.roadMiles, 0).toFixed(0)}</p>
        <p class="text-xs text-gray-400">Total run {distanceLabel}</p>
      </div>
      <div class="text-center">
        <p class="text-lg font-bold text-strength-500">{weeklyData.reduce((sum, w) => sum + w.strengthCount, 0)}</p>
        <p class="text-xs text-gray-400">Strength sessions</p>
      </div>
    </div>
  {:else}
    <div class="h-48 flex items-center justify-center text-gray-400">
      <p>No training data yet</p>
    </div>
  {/if}
</div>
