<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { weightFromMetric, getWeightLabel } from '$lib/utils/units';
  import type { WeightUnit } from '$lib/api/client';

  export let weight: number | null = null;
  export let weightDate: string | null = null;
  export let weightChange: number | null = null;
  export let weightUnit: WeightUnit = 'kg';
</script>

<div class="card p-6">
  <p class="text-sm text-gray-500 mb-1">Current Weight</p>
  <div class="flex items-baseline gap-2">
    <p class="text-4xl font-bold">
      {weight ? weightFromMetric(weight, weightUnit).toFixed(2) : '—'}
    </p>
    {#if weight}
      <span class="text-lg text-gray-400">{getWeightLabel(weightUnit)}</span>
    {/if}
  </div>
  {#if weightDate}
    <p class="text-xs text-gray-400 mt-1">
      as of {format(parseISO(weightDate), 'MMM d, yyyy')}
    </p>
  {/if}
  {#if weightChange !== null}
    <p class="text-sm mt-2 {weightChange < 0 ? 'text-green-500' : weightChange > 0 ? 'text-red-500' : 'text-gray-400'}">
      {weightChange > 0 ? '+' : ''}{weightFromMetric(weightChange, weightUnit).toFixed(2)} {getWeightLabel(weightUnit)} over 30 days
    </p>
  {/if}
</div>
