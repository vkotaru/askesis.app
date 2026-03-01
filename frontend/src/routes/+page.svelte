<script lang="ts">
  import { onMount } from 'svelte';
  import { format, subDays } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets, Activity, TrendingUp } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type DailyLog, type Activity as ActivityType } from '$lib/api/client';

  let logs: DailyLog[] = [];
  let activities: ActivityType[] = [];
  let loading = true;

  const today = format(new Date(), 'yyyy-MM-dd');
  const weekAgo = format(subDays(new Date(), 7), 'yyyy-MM-dd');

  onMount(async () => {
    try {
      [logs, activities] = await Promise.all([
        api.getDailyLogs(weekAgo, today),
        api.getActivities(weekAgo, today),
      ]);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      loading = false;
    }
  });

  $: todayLog = logs.find((l) => l.date === today);
  $: weightData = logs.filter((l) => l.weight).reverse();
</script>

<svelte:head>
  <title>Dashboard - Askesis</title>
</svelte:head>

<div>
  <div class="mb-8">
    <h1 class="text-2xl font-bold">Dashboard</h1>
    <p class="text-gray-500 text-sm mt-1">
      {format(new Date(), 'EEEE, MMMM d, yyyy')}
    </p>
  </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else}
    <!-- Today's snapshot -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="card p-4">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Weight</p>
            <p class="text-2xl font-bold">
              {todayLog?.weight ?? '—'}
              {#if todayLog?.weight}
                <span class="text-sm font-normal text-gray-400 ml-1">kg</span>
              {/if}
            </p>
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
              {todayLog?.sleep_hours ?? '—'}
              {#if todayLog?.sleep_hours}
                <span class="text-sm font-normal text-gray-400 ml-1">hrs</span>
              {/if}
            </p>
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
            <p class="text-2xl font-bold">{todayLog?.steps ?? '—'}</p>
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
              {todayLog?.water_ml ?? '—'}
              {#if todayLog?.water_ml}
                <span class="text-sm font-normal text-gray-400 ml-1">ml</span>
              {/if}
            </p>
          </div>
          <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
            <Droplets size={20} class="text-cardio-400" />
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Weight trend placeholder -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-4">
          <TrendingUp size={20} class="text-primary-500" />
          <h2 class="text-lg font-semibold">Weight Trend</h2>
          <span class="text-sm text-gray-400 ml-auto">Last 7 days</span>
        </div>
        {#if weightData.length > 0}
          <div class="h-64 flex items-end gap-2">
            {#each weightData as log}
              <div class="flex-1 flex flex-col items-center gap-2">
                <div
                  class="w-full bg-primary-400 rounded-t"
                  style="height: {((log.weight || 0) - 50) * 4}px; min-height: 20px;"
                ></div>
                <span class="text-xs text-gray-500">{format(new Date(log.date), 'EEE')}</span>
              </div>
            {/each}
          </div>
        {:else}
          <div class="h-64 flex items-center justify-center text-gray-400">
            <p>No weight data yet. Start logging!</p>
          </div>
        {/if}
      </div>

      <!-- Recent activities -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-4">
          <Activity size={20} class="text-cardio-500" />
          <h2 class="text-lg font-semibold">Recent Activities</h2>
        </div>
        {#if activities.length > 0}
          <ul class="space-y-3">
            {#each activities.slice(0, 5) as activity}
              <li class="flex items-center justify-between py-3 px-4 rounded-lg bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                <div>
                  <p class="font-medium">{activity.name}</p>
                  <p class="text-sm text-gray-500">
                    {format(new Date(activity.date), 'MMM d')}
                    {#if activity.duration_mins} · {activity.duration_mins} min{/if}
                    {#if activity.distance_km} · {activity.distance_km} km{/if}
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
    </div>
  {/if}
</div>
