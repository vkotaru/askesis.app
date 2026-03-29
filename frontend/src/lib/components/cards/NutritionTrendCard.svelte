<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { Flame } from 'lucide-svelte';

  export let chartData: { date: string; calories: number; protein: number }[] = [];

  let hoveredPoint: { x: number; y: number; calories: number; protein: number; date: string } | null = null;

  const chartWidth = 400;
  const chartHeight = 200;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  $: caloriesMax = Math.max(...chartData.map(d => d.calories), 100);
  $: proteinMax = Math.max(...chartData.map(d => d.protein), 10);
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-4">
    <Flame size={20} class="text-nutrition-500" />
    <h2 class="text-lg font-semibold">Calories & Protein</h2>
    <span class="text-xs text-gray-400 ml-auto">Last 30 days</span>
  </div>
  {#if chartData.length > 0}
    <div class="relative" style="aspect-ratio: 2/1;">
      <svg
        viewBox="0 0 {chartWidth} {chartHeight}"
        class="w-full h-full"
        on:mouseleave={() => hoveredPoint = null}
      >
        {#each [0, 0.25, 0.5, 0.75, 1] as tick}
          <line x1={padding.left} y1={padding.top + innerHeight * (1 - tick)}
            x2={chartWidth - padding.right} y2={padding.top + innerHeight * (1 - tick)}
            stroke="currentColor" stroke-opacity="0.1" stroke-dasharray="4,4" />
        {/each}

        {#if chartData.length > 1}
          <path
            d={chartData.map((d, i) => {
              const x = padding.left + (i / (chartData.length - 1)) * innerWidth;
              const y = padding.top + innerHeight - (d.calories / caloriesMax) * innerHeight;
              return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
            }).join(' ')}
            fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" class="text-nutrition-500"
          />
          {@const nutDotR = chartData.length > 20 ? 2.5 : 4}
          {#each chartData as d, i}
            {@const x = padding.left + (i / (chartData.length - 1)) * innerWidth}
            {@const y = padding.top + innerHeight - (d.calories / caloriesMax) * innerHeight}
            <circle cx={x} cy={y} r={nutDotR} class="fill-nutrition-500 cursor-pointer"
              on:mouseenter={() => hoveredPoint = { x, y, calories: d.calories, protein: d.protein, date: d.date }} />
          {/each}

          <path
            d={chartData.map((d, i) => {
              const x = padding.left + (i / (chartData.length - 1)) * innerWidth;
              const y = padding.top + innerHeight - (d.protein / proteinMax) * innerHeight;
              return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
            }).join(' ')}
            fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" class="text-strength-500"
          />
          {#each chartData as d, i}
            {@const x = padding.left + (i / (chartData.length - 1)) * innerWidth}
            {@const y = padding.top + innerHeight - (d.protein / proteinMax) * innerHeight}
            <circle cx={x} cy={y} r={chartData.length > 20 ? 2 : 3} class="fill-strength-500" />
          {/each}
        {/if}

        <text x={padding.left - 8} y={padding.top} text-anchor="end" dominant-baseline="middle" class="fill-nutrition-500 text-[9px] font-medium">{Math.round(caloriesMax)}</text>
        <text x={padding.left - 8} y={padding.top + innerHeight / 2} text-anchor="end" dominant-baseline="middle" class="fill-nutrition-500 text-[9px]">{Math.round(caloriesMax / 2)}</text>
        <text x={padding.left - 8} y={padding.top + innerHeight} text-anchor="end" dominant-baseline="middle" class="fill-nutrition-500 text-[9px]">0</text>

        <text x={chartWidth - padding.right + 8} y={padding.top} text-anchor="start" dominant-baseline="middle" class="fill-strength-500 text-[9px] font-medium">{Math.round(proteinMax)}g</text>
        <text x={chartWidth - padding.right + 8} y={padding.top + innerHeight / 2} text-anchor="start" dominant-baseline="middle" class="fill-strength-500 text-[9px]">{Math.round(proteinMax / 2)}g</text>
        <text x={chartWidth - padding.right + 8} y={padding.top + innerHeight} text-anchor="start" dominant-baseline="middle" class="fill-strength-500 text-[9px]">0</text>

        {#if chartData.length > 0}
          <text x={padding.left} y={chartHeight - 8} text-anchor="start" class="fill-gray-400 text-[9px]">
            {format(parseISO(chartData[0].date), 'MMM d')}
          </text>
          <text x={chartWidth - padding.right} y={chartHeight - 8} text-anchor="end" class="fill-gray-400 text-[9px]">
            {format(parseISO(chartData[chartData.length - 1].date), 'MMM d')}
          </text>
        {/if}
      </svg>

      {#if hoveredPoint}
        <div
          class="absolute bg-gray-900 text-white text-xs px-2 py-1 rounded shadow-lg pointer-events-none z-10"
          style="left: {(hoveredPoint.x / chartWidth) * 100}%; top: {(hoveredPoint.y / chartHeight) * 100 - 10}%; transform: translateX(-50%);"
        >
          <div class="font-medium text-nutrition-300">{hoveredPoint.calories} cal</div>
          <div class="text-strength-300">{hoveredPoint.protein}g protein</div>
          <div class="text-gray-300">{format(parseISO(hoveredPoint.date), 'MMM d')}</div>
        </div>
      {/if}
    </div>

    <div class="flex items-center justify-center gap-6 mt-4 text-xs text-gray-500">
      <div class="flex items-center gap-2">
        <div class="w-4 h-0.5 bg-nutrition-500 rounded"></div>
        <span>Calories (left)</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-4 h-0.5 bg-strength-500 rounded"></div>
        <span>Protein g (right)</span>
      </div>
    </div>
  {:else}
    <div class="h-48 flex items-center justify-center text-gray-400">
      <p>No nutrition data yet</p>
    </div>
  {/if}
</div>
