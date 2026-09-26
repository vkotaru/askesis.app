<script lang="ts">
  /**
   * The three numbers worth seeing before anything else: weight, sleep, steps.
   *
   * Each is the most recent figure on record, not today's — a blank card at 9am
   * every morning would be worse than useless. When the reading is not from
   * today the date is shown underneath, so a stale number never passes for a
   * current one.
   *
   * Tapping one jumps to its chart further down the page. The snapshot answers
   * "where am I", the chart answers "which way am I going", and they are the
   * same question asked twice — so the card is the way into the trend rather
   * than a dead end beside it. The parent owns the scrolling: this component
   * only says which metric was tapped, so it does not need to know what the page
   * around it looks like.
   *
   * Water used to sit here as a fourth. It was removed because it was never
   * logged, and a permanently empty card is worse than no card: it takes the
   * space that lets the other three sit on one line.
   */
  import { createEventDispatcher } from 'svelte';
  import { format } from 'date-fns';
  import { Scale, Moon, Footprints, ChevronRight } from 'lucide-svelte';
  import { settings } from '$lib/stores/settings';
  import { weightFromMetric, getWeightLabel } from '$lib/utils/units';
  import type { DailyLog } from '$lib/api/client';

  export let logs: DailyLog[] = [];

  const dispatch = createEventDispatcher<{ jump: 'weight' | 'sleep' | 'steps' }>();

  const today = format(new Date(), 'yyyy-MM-dd');

  $: latestWeightLog = logs.find((l) => l.weight);
  $: latestSleepLog = logs.find((l) => l.sleep_hours);
  $: latestStepsLog = logs.find((l) => l.steps);

  $: tiles = [
    {
      key: 'weight' as const,
      label: 'Weight',
      value: latestWeightLog?.weight
        ? weightFromMetric(latestWeightLog.weight, $settings.weight_unit).toFixed(2)
        : '—',
      suffix: latestWeightLog?.weight ? getWeightLabel($settings.weight_unit) : '',
      asOf: latestWeightLog?.date,
      icon: Scale,
      iconClass: 'text-rest-500',
      tintClass: 'bg-rest-100 dark:bg-rest-900/30',
    },
    {
      key: 'sleep' as const,
      label: 'Sleep',
      value: latestSleepLog?.sleep_hours != null ? String(latestSleepLog.sleep_hours) : '—',
      suffix: latestSleepLog?.sleep_hours != null ? 'hrs' : '',
      asOf: latestSleepLog?.date,
      icon: Moon,
      iconClass: 'text-strength-500',
      tintClass: 'bg-strength-100 dark:bg-strength-900/30',
    },
    {
      key: 'steps' as const,
      label: 'Steps',
      value: latestStepsLog?.steps != null ? latestStepsLog.steps.toLocaleString() : '—',
      suffix: '',
      asOf: latestStepsLog?.date,
      icon: Footprints,
      iconClass: 'text-cardio-500',
      tintClass: 'bg-cardio-100 dark:bg-cardio-900/30',
    },
  ];
</script>

<div class="grid grid-cols-3 gap-2 sm:gap-4">
  {#each tiles as tile}
    <button
      type="button"
      class="card p-3 sm:p-4 text-left w-full cursor-pointer hover:border-primary-300 dark:hover:border-primary-700 transition-colors group"
      aria-label="{tile.label}: {tile.value} {tile.suffix}. Show the trend."
      on:click={() => dispatch('jump', tile.key)}
    >
      <div class="flex items-start justify-between gap-1">
        <div class="min-w-0">
          <p class="text-xs sm:text-sm text-gray-500 mb-0.5 sm:mb-1 flex items-center gap-0.5">
            {tile.label}
            <ChevronRight
              size={12}
              class="text-gray-300 group-hover:text-primary-400 transition-colors"
            />
          </p>
          <p class="text-lg sm:text-xl md:text-2xl font-bold whitespace-nowrap tabular-nums">
            {tile.value}
            {#if tile.suffix}
              <span class="text-xs sm:text-sm font-normal text-gray-400 ml-0.5">{tile.suffix}</span>
            {/if}
          </p>
          <!-- The slot is always here, so the three tiles stay the same height
               whether or not a reading happens to be from today. -->
          <p class="text-[10px] sm:text-xs text-gray-400 mt-0.5 sm:mt-1 h-3.5">
            {tile.asOf && tile.asOf !== today ? format(new Date(tile.asOf), 'MMM d') : ''}
          </p>
        </div>
        <div class="p-1.5 sm:p-2 rounded-lg {tile.tintClass} shrink-0">
          <svelte:component this={tile.icon} size={18} class={tile.iconClass} />
        </div>
      </div>
    </button>
  {/each}
</div>
