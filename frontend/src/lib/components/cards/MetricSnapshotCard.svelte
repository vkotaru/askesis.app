<script lang="ts">
  import { format } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets } from 'lucide-svelte';
  import { settings } from '$lib/stores/settings';
  import { weightFromMetric, formatWater, getWeightLabel } from '$lib/utils/units';
  import type { DailyLog } from '$lib/api/client';

  export let logs: DailyLog[] = [];

  const today = format(new Date(), 'yyyy-MM-dd');

  $: latestWeightLog = logs.find((l) => l.weight);
  $: latestSleepLog = logs.find((l) => l.sleep_hours);
  $: latestStepsLog = logs.find((l) => l.steps);
  $: latestWaterLog = logs.find((l) => l.water_ml);
</script>

<div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
  <div class="card p-4">
    <div class="flex items-start justify-between">
      <div>
        <p class="text-sm text-gray-500 mb-1">Weight</p>
        <p class="text-2xl font-bold">
          {latestWeightLog?.weight ? weightFromMetric(latestWeightLog.weight, $settings.weight_unit).toFixed(2) : '—'}
          {#if latestWeightLog?.weight}
            <span class="text-sm font-normal text-gray-400 ml-1">{getWeightLabel($settings.weight_unit)}</span>
          {/if}
        </p>
        {#if latestWeightLog && latestWeightLog.date !== today}
          <p class="text-xs text-gray-400 mt-1">{format(new Date(latestWeightLog.date), 'MMM d')}</p>
        {/if}
      </div>
      <div class="p-2 rounded-lg bg-rest-100 dark:bg-rest-900/30">
        <Scale size={20} class="text-rest-500" />
      </div>
    </div>
  </div>

  <div class="card p-4">
    <div class="flex items-start justify-between">
      <div>
        <p class="text-sm text-gray-500 mb-1">Sleep</p>
        <p class="text-2xl font-bold">
          {latestSleepLog?.sleep_hours ?? '—'}
          {#if latestSleepLog?.sleep_hours}
            <span class="text-sm font-normal text-gray-400 ml-1">hrs</span>
          {/if}
        </p>
        {#if latestSleepLog && latestSleepLog.date !== today}
          <p class="text-xs text-gray-400 mt-1">{format(new Date(latestSleepLog.date), 'MMM d')}</p>
        {/if}
      </div>
      <div class="p-2 rounded-lg bg-strength-100 dark:bg-strength-900/30">
        <Moon size={20} class="text-strength-500" />
      </div>
    </div>
  </div>

  <div class="card p-4">
    <div class="flex items-start justify-between">
      <div>
        <p class="text-sm text-gray-500 mb-1">Steps</p>
        <p class="text-2xl font-bold">{latestStepsLog?.steps ?? '—'}</p>
        {#if latestStepsLog && latestStepsLog.date !== today}
          <p class="text-xs text-gray-400 mt-1">{format(new Date(latestStepsLog.date), 'MMM d')}</p>
        {/if}
      </div>
      <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
        <Footprints size={20} class="text-cardio-500" />
      </div>
    </div>
  </div>

  <div class="card p-4">
    <div class="flex items-start justify-between">
      <div>
        <p class="text-sm text-gray-500 mb-1">Water</p>
        <p class="text-2xl font-bold">
          {formatWater(latestWaterLog?.water_ml, $settings.water_unit)}
        </p>
        {#if latestWaterLog && latestWaterLog.date !== today}
          <p class="text-xs text-gray-400 mt-1">{format(new Date(latestWaterLog.date), 'MMM d')}</p>
        {/if}
      </div>
      <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
        <Droplets size={20} class="text-cardio-400" />
      </div>
    </div>
  </div>
</div>
