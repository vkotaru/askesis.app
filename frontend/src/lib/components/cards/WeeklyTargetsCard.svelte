<script lang="ts">
  import { Target, Check } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import type { Activity } from '$lib/api/client';
  import { distanceFromMetric, getDistanceLabel } from '$lib/utils/units';
  import type { DistanceUnit } from '$lib/api/client';
  import {
    DISCIPLINE_BY_KEY,
    completedDisciplines,
    distanceFor,
    parsePlan,
  } from '$lib/utils/disciplines';

  /** This week's activities — already week-scoped by the caller. */
  export let activities: Activity[] = [];
  /** Targets in km (canonical metric); null means "no target set". */
  export let runKm: number | null = null;
  export let bikeKm: number | null = null;
  /** Comma-separated discipline keys from user_settings. */
  export let disciplines: string | null = null;
  export let distanceUnit: DistanceUnit = 'km';

  $: unitLabel = getDistanceLabel(distanceUnit);
  $: plan = parsePlan(disciplines);
  $: done = completedDisciplines(activities);

  // Distances are stored and compared in km, and converted only for display —
  // switching units must not move the goalposts.
  $: bars = [
    { key: 'run' as const, target: runKm },
    { key: 'bike' as const, target: bikeKm },
  ]
    .filter((b) => b.target && b.target > 0)
    .map((b) => {
      const actualKm = distanceFor(activities, b.key);
      return {
        ...b,
        label: DISCIPLINE_BY_KEY[b.key].label,
        icon: DISCIPLINE_BY_KEY[b.key].icon,
        actual: distanceFromMetric(actualKm, distanceUnit),
        goal: distanceFromMetric(b.target as number, distanceUnit),
        // Clamped for the bar width only; the number above it still shows the
        // overshoot, because beating a target is worth seeing.
        pct: Math.min(100, (actualKm / (b.target as number)) * 100),
        hit: actualKm >= (b.target as number),
      };
    });

  $: configured = bars.length > 0 || plan.length > 0;
  $: doneCount = plan.filter((k) => done.has(k)).length;
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-4">
    <Target size={20} class="text-primary-500" />
    <h2 class="text-lg font-semibold">Weekly Targets</h2>
    {#if plan.length > 0}
      <span class="text-xs text-gray-400 ml-auto">{doneCount}/{plan.length} disciplines</span>
    {/if}
  </div>

  {#if !configured}
    <p class="text-sm text-gray-400 py-6 text-center">
      No weekly plan yet — set your targets in
      <a href="/settings" class="text-primary-500 hover:underline">Settings</a>.
    </p>
  {:else}
    {#each bars as bar}
      {@const Icon = bar.icon}
      <div class="mb-4">
        <div class="flex items-center gap-2 mb-1.5 text-sm">
          <Icon size={14} class={bar.hit ? 'text-primary-500' : 'text-gray-400'} />
          <span class="font-medium">{bar.label}</span>
          <span class="ml-auto tabular-nums">
            <span class={clsx('font-semibold', bar.hit && 'text-primary-500')}>
              {bar.actual.toFixed(1)}
            </span>
            <span class="text-gray-400">/ {bar.goal.toFixed(0)} {unitLabel}</span>
          </span>
        </div>
        <div class="h-2.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
          <div
            class={clsx(
              'h-full rounded-full transition-all duration-500',
              bar.hit ? 'bg-primary-500' : 'bg-cardio-400'
            )}
            style="width: {bar.pct}%"
          ></div>
        </div>
      </div>
    {/each}

    {#if plan.length > 0}
      <div class={clsx('flex flex-wrap gap-2', bars.length > 0 && 'mt-5 pt-4 border-t border-gray-200 dark:border-gray-700')}>
        {#each plan as key}
          {@const d = DISCIPLINE_BY_KEY[key]}
          {@const isDone = done.has(key)}
          {@const Icon = d.icon}
          <div
            class={clsx(
              'flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm transition-all',
              isDone
                ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
                : 'bg-gray-100 dark:bg-gray-700/50 text-gray-400 dark:text-gray-500'
            )}
            title={isDone ? `${d.label} — done this week` : `${d.label} — not yet`}
          >
            <Icon size={15} />
            <span>{d.label}</span>
            {#if isDone}<Check size={13} />{/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>
