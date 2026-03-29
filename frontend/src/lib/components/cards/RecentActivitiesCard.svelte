<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import { Activity } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { formatDistance } from '$lib/utils/units';
  import type { Activity as ActivityType, DistanceUnit } from '$lib/api/client';

  export let activities: ActivityType[] = [];
  export let distanceUnit: DistanceUnit = 'km';
  export let limit: number = 5;
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-4">
    <Activity size={20} class="text-cardio-500" />
    <h2 class="text-lg font-semibold">Recent Activities</h2>
  </div>
  {#if activities.length > 0}
    <ul class="space-y-3">
      {#each activities.slice(0, limit) as activity}
        <li class="flex items-center justify-between py-3 px-4 rounded-lg bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
          <div>
            <p class="font-medium">{activity.name}</p>
            <p class="text-sm text-gray-500">
              {format(parseISO(activity.date), 'MMM d')}
              {#if activity.duration_mins} · {activity.duration_mins} min{/if}
              {#if activity.distance_km} · {formatDistance(activity.distance_km, distanceUnit)}{/if}
            </p>
          </div>
          <span
            class={clsx(
              'text-xs px-3 py-1 rounded-full font-medium',
              activity.activity_type === 'cardio'
                ? 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400'
                : 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400'
            )}
          >
            {activity.activity_type}
          </span>
        </li>
      {/each}
    </ul>
  {:else}
    <div class="h-48 flex items-center justify-center text-gray-400">
      <p>No activities yet. Let's get moving!</p>
    </div>
  {/if}
</div>
