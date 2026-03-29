<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { measurementFromMetric, getMeasurementLabel } from '$lib/utils/units';
  import type { MeasurementUnit } from '$lib/api/client';

  interface MeasurementSnapshot {
    date: string;
    neck: number | null;
    shoulders: number | null;
    chest: number | null;
    bicep_left: number | null;
    bicep_right: number | null;
    waist: number | null;
    abdomen: number | null;
    hips: number | null;
    thigh_left: number | null;
    thigh_right: number | null;
    calf_left: number | null;
    calf_right: number | null;
  }

  export let latest: MeasurementSnapshot;
  export let previous: MeasurementSnapshot | null = null;
  export let measurementUnit: MeasurementUnit = 'cm';

  const FIELDS: [string, keyof MeasurementSnapshot][] = [
    ['Chest', 'chest'], ['Waist', 'waist'], ['Hips', 'hips'],
    ['Shoulders', 'shoulders'], ['Neck', 'neck'], ['Abdomen', 'abdomen'],
    ['Bicep L', 'bicep_left'], ['Bicep R', 'bicep_right'],
    ['Thigh L', 'thigh_left'], ['Thigh R', 'thigh_right'],
    ['Calf L', 'calf_left'], ['Calf R', 'calf_right'],
  ];

  $: mLabel = getMeasurementLabel(measurementUnit);
</script>

<div class="card p-6">
  <h2 class="text-sm font-semibold text-gray-500 mb-4">Body Measurements</h2>
  <div class="grid grid-cols-3 gap-2 mb-3 text-[10px] text-gray-400 uppercase tracking-wide">
    <span></span>
    <span class="text-right">{format(parseISO(latest.date), 'MMM d')}</span>
    {#if previous}
      <span class="text-right">{format(parseISO(previous.date), 'MMM d')}</span>
    {/if}
  </div>
  {#each FIELDS as [label, key]}
    {@const latestCm = Number(latest[key]) || 0}
    {@const prevCm = previous ? Number(previous[key]) || 0 : 0}
    {@const latestVal = latestCm > 0 ? measurementFromMetric(latestCm, measurementUnit) : 0}
    {@const prevVal = prevCm > 0 ? measurementFromMetric(prevCm, measurementUnit) : 0}
    {#if latestVal > 0 || prevVal > 0}
      <div class="grid grid-cols-3 gap-2 py-1.5 border-b border-gray-50 dark:border-gray-700/50 last:border-0">
        <span class="text-xs text-gray-500">{label}</span>
        <span class="text-xs font-semibold text-right">
          {latestVal > 0 ? `${latestVal.toFixed(1)} ${mLabel}` : '—'}
        </span>
        {#if previous}
          <span class="text-xs text-right text-gray-400">
            {prevVal > 0 ? `${prevVal.toFixed(1)} ${mLabel}` : '—'}
            {#if latestVal > 0 && prevVal > 0}
              {@const diff = latestVal - prevVal}
              {#if diff !== 0}
                <span class="ml-1 {diff > 0 ? 'text-green-500' : 'text-red-500'}">{diff > 0 ? '+' : ''}{diff.toFixed(1)}</span>
              {/if}
            {/if}
          </span>
        {/if}
      </div>
    {/if}
  {/each}
</div>
