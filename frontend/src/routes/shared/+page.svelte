<script lang="ts">
  import { onMount } from 'svelte';
  import { format, subDays, parseISO } from 'date-fns';
  import { Scale, Moon, Footprints, Droplets, Activity, Users, TrendingUp, TrendingDown, Dumbbell, ChevronDown } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type DailyLog, type Activity as ActivityType, type SharedWithMe } from '$lib/api/client';
  import { settings } from '$lib/stores/settings';
  import { formatWeight, weightFromMetric, formatWater, getWeightLabel } from '$lib/utils/units';
  import { getActivityIcon, LEGEND_ICONS } from '$lib/utils/activityIcons';

  interface UserData {
    user: { id: number | null; name: string; picture?: string };
    logs: DailyLog[];
    activities: ActivityType[];
    latestWeight?: DailyLog;
    latestSleep?: DailyLog;
    latestSteps?: DailyLog;
    latestWater?: DailyLog;
    weightData: DailyLog[];
  }

  let loadingShares = true;
  let loading = false;
  let userData: UserData[] = [];
  let availableUsers: SharedWithMe[] = [];
  let selectedUserId: number | null = null;

  const CACHE_KEY = 'shared_dashboard_last_user';

  const today = format(new Date(), 'yyyy-MM-dd');
  const thirtyDaysAgo = format(subDays(new Date(), 30), 'yyyy-MM-dd');

  onMount(async () => {
    try {
      availableUsers = await api.getSharedWithMe();
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) {
        const cachedId = Number(cached);
        if (availableUsers.some(u => u.owner_id === cachedId && u.categories.includes('daily_logs'))) {
          selectedUserId = cachedId;
        }
      }
    } catch {
      availableUsers = [];
    } finally {
      loadingShares = false;
    }
  });

  async function loadComparison() {
    const selected = availableUsers.find(u => u.owner_id === selectedUserId);
    if (!selected) return;

    loading = true;
    try {
      const [myData, theirData] = await Promise.all([
        loadUserData(null, 'Me'),
        loadUserData(selected.owner_id, selected.owner_name, selected.owner_picture),
      ]);
      userData = [myData, theirData];
    } catch (err) {
      console.error('Failed to load shared dashboard data:', err);
    } finally {
      loading = false;
    }
  }

  $: if (selectedUserId !== null) {
    localStorage.setItem(CACHE_KEY, String(selectedUserId));
    loadComparison();
  }

  async function loadUserData(userId: number | null, name: string, picture?: string): Promise<UserData> {
    const [logs, activities] = await Promise.all([
      api.getDailyLogs(undefined, undefined, userId ?? undefined, 60),
      api.getActivities(thirtyDaysAgo, today, userId ?? undefined, 10),
    ]);

    const weightData = logs.filter(l => l.weight).slice().reverse();

    return {
      user: { id: userId, name, picture },
      logs,
      activities,
      latestWeight: logs.find(l => l.weight),
      latestSleep: logs.find(l => l.sleep_hours),
      latestSteps: logs.find(l => l.steps),
      latestWater: logs.find(l => l.water_ml),
      weightData,
    };
  }

  // Chart dimensions
  const chartWidth = 400;
  const chartHeight = 180;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  // Colors for different users
  const userColors = ['text-primary-500', 'text-accent-500', 'text-cardio-500', 'text-strength-500'];
  const userFills = ['fill-primary-500', 'fill-accent-500', 'fill-cardio-500', 'fill-strength-500'];

  // Calculate normalized weight data (percentage change from starting weight)
  // Each user's first data point = 0%, subsequent points show % change
  $: normalizedWeightData = userData.map(u => {
    if (u.weightData.length === 0) return { startWeight: 0, changes: [] };
    const startWeight = u.weightData[0].weight || 0;
    const changes = u.weightData.map(log => {
      const weight = log.weight || 0;
      const percentChange = startWeight > 0 ? ((weight - startWeight) / startWeight) * 100 : 0;
      return { date: log.date, percentChange };
    });
    return { startWeight, changes };
  });

  // Find min/max percent change across all users
  $: allChanges = normalizedWeightData.flatMap(u => u.changes.map(c => c.percentChange));
  $: changeMin = allChanges.length > 0 ? Math.min(...allChanges, 0) - 1 : -5;
  $: changeMax = allChanges.length > 0 ? Math.max(...allChanges, 0) + 1 : 5;
  $: changeRange = changeMax - changeMin || 1;

  // Generate normalized weight path for a user
  function generateNormalizedPath(changes: { date: string; percentChange: number }[]): string {
    if (changes.length < 2) return '';
    return changes.map((c, i) => {
      const x = padding.left + (i / (changes.length - 1)) * innerWidth;
      const y = padding.top + innerHeight - (c.percentChange - changeMin) / changeRange * innerHeight;
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');
  }

  // Calculate where 0% line should be
  $: zeroLineY = padding.top + innerHeight - (0 - changeMin) / changeRange * innerHeight;

  // Combine all activities and sort by date (newest first)
  $: allActivities = userData
    .flatMap((u, idx) => u.activities.map(a => ({ ...a, userName: u.user.name, userIndex: idx })))
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 10);

  // Last 5 days for activity grid
  $: last5Days = Array.from({ length: 5 }, (_, i) => {
    const d = subDays(new Date(), i);
    return { date: format(d, 'yyyy-MM-dd'), display: format(d, 'EEE, MMM d') };
  });

  // Group activities by date for each user
  $: activitiesByUserAndDate = userData.map((u, idx) => {
    const byDate: Record<string, ActivityType[]> = {};
    for (const day of last5Days) {
      byDate[day.date] = u.activities.filter(a => a.date === day.date);
    }
    return { userIndex: idx, userName: u.user.name, byDate };
  });
</script>

<svelte:head>
  <title>Shared Dashboard - Askesis</title>
</svelte:head>

<div>
  <div class="mb-8">
    <h1 class="text-2xl font-bold flex items-center gap-2">
      <Users size={24} class="text-accent-500" />
      Shared Dashboard
    </h1>
    <p class="text-gray-500 text-sm mt-1">
      Compare progress with your accountability partners
    </p>
  </div>

  {#if loadingShares}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else if availableUsers.length === 0}
    <div class="card p-12 text-center">
      <Users size={48} class="mx-auto mb-4 text-gray-300" />
      <h2 class="text-lg font-semibold mb-2">No shared data yet</h2>
      <p class="text-gray-500 mb-4">
        Ask someone to share their data with you, or share your data with them in Settings.
      </p>
      <a href="/settings" class="btn btn-primary">Go to Settings</a>
    </div>
  {:else}
    <!-- User selector -->
    <div class="card p-4 mb-6">
      <label for="compare-user" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        Compare against
      </label>
      <select
        id="compare-user"
        bind:value={selectedUserId}
        class="input max-w-xs"
      >
        <option value={null}>Select a person...</option>
        {#each availableUsers.filter(u => u.categories.includes('daily_logs')) as user}
          <option value={user.owner_id}>
            {user.owner_name}
          </option>
        {/each}
      </select>
    </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else if userData.length < 2}
    <div class="card p-12 text-center text-gray-500">
      <p>Select a person above to compare your progress.</p>
    </div>
  {:else}
    <!-- User avatars/names header -->
    <div class="flex items-center gap-4 mb-6">
      {#each userData as { user }, idx}
        <div class="flex items-center gap-2">
          <div class={clsx(
            'w-3 h-3 rounded-full',
            idx === 0 ? 'bg-primary-500' : idx === 1 ? 'bg-accent-500' : 'bg-cardio-500'
          )}></div>
          {#if user.picture}
            <img src={user.picture} alt={user.name} class="w-8 h-8 rounded-full" />
          {:else}
            <div class="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-sm font-medium">
              {user.name.charAt(0).toUpperCase()}
            </div>
          {/if}
          <span class="font-medium">{user.name}</span>
        </div>
      {/each}
    </div>

    <!-- Today's metrics comparison -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <!-- Weight -->
      <div class="card p-4">
        <div class="flex items-center gap-2 mb-3">
          <div class="p-2 rounded-lg bg-rest-100 dark:bg-rest-900/30">
            <Scale size={18} class="text-rest-500" />
          </div>
          <span class="text-sm text-gray-500">Weight</span>
        </div>
        <div class="space-y-2">
          {#each userData as { user, latestWeight }, idx}
            <div class="flex items-center justify-between">
              <span class={clsx('text-xs font-medium', userColors[idx])}>{user.name}</span>
              <span class="font-bold">
                {latestWeight?.weight ? weightFromMetric(latestWeight.weight, $settings.weight_unit).toFixed(1) : '—'}
                {#if latestWeight?.weight}
                  <span class="text-xs font-normal text-gray-400">{getWeightLabel($settings.weight_unit)}</span>
                {/if}
              </span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Sleep -->
      <div class="card p-4">
        <div class="flex items-center gap-2 mb-3">
          <div class="p-2 rounded-lg bg-strength-100 dark:bg-strength-900/30">
            <Moon size={18} class="text-strength-500" />
          </div>
          <span class="text-sm text-gray-500">Sleep</span>
        </div>
        <div class="space-y-2">
          {#each userData as { user, latestSleep }, idx}
            <div class="flex items-center justify-between">
              <span class={clsx('text-xs font-medium', userColors[idx])}>{user.name}</span>
              <span class="font-bold">
                {latestSleep?.sleep_hours ?? '—'}
                {#if latestSleep?.sleep_hours}
                  <span class="text-xs font-normal text-gray-400">hrs</span>
                {/if}
              </span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Steps -->
      <div class="card p-4">
        <div class="flex items-center gap-2 mb-3">
          <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
            <Footprints size={18} class="text-cardio-500" />
          </div>
          <span class="text-sm text-gray-500">Steps</span>
        </div>
        <div class="space-y-2">
          {#each userData as { user, latestSteps }, idx}
            <div class="flex items-center justify-between">
              <span class={clsx('text-xs font-medium', userColors[idx])}>{user.name}</span>
              <span class="font-bold">
                {latestSteps?.steps?.toLocaleString() ?? '—'}
              </span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Water -->
      <div class="card p-4">
        <div class="flex items-center gap-2 mb-3">
          <div class="p-2 rounded-lg bg-cardio-100 dark:bg-cardio-900/30">
            <Droplets size={18} class="text-cardio-400" />
          </div>
          <span class="text-sm text-gray-500">Water</span>
        </div>
        <div class="space-y-2">
          {#each userData as { user, latestWater }, idx}
            <div class="flex items-center justify-between">
              <span class={clsx('text-xs font-medium', userColors[idx])}>{user.name}</span>
              <span class="font-bold">
                {formatWater(latestWater?.water_ml, $settings.water_unit)}
              </span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Combined Weight Chart -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-4">
          <TrendingUp size={20} class="text-primary-500" />
          <h2 class="text-lg font-semibold">Weight Comparison</h2>
          <span class="text-xs text-gray-400 ml-auto">Last 30 days</span>
        </div>

        {#if userData.some(u => u.weightData.length > 0)}
          <div class="relative" style="aspect-ratio: 2/1;">
            <svg viewBox="0 0 {chartWidth} {chartHeight}" class="w-full h-full">
              <!-- Grid lines -->
              {#each [0, 0.25, 0.5, 0.75, 1] as tick}
                <line
                  x1={padding.left}
                  y1={padding.top + innerHeight * (1 - tick)}
                  x2={chartWidth - padding.right}
                  y2={padding.top + innerHeight * (1 - tick)}
                  stroke="currentColor"
                  stroke-opacity="0.1"
                  stroke-dasharray="4,4"
                />
              {/each}

              <!-- Zero line (baseline) -->
              <line
                x1={padding.left}
                y1={zeroLineY}
                x2={chartWidth - padding.right}
                y2={zeroLineY}
                stroke="currentColor"
                stroke-opacity="0.3"
                class="text-gray-500"
              />

              <!-- Weight lines for each user (normalized) -->
              {#each normalizedWeightData as { changes }, idx}
                {@const path = generateNormalizedPath(changes)}
                {#if path}
                  <path
                    d={path}
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    class={userColors[idx]}
                  />
                  <!-- Data points -->
                  {#each changes as c, i}
                    {@const x = padding.left + (changes.length > 1 ? (i / (changes.length - 1)) * innerWidth : innerWidth / 2)}
                    {@const y = padding.top + innerHeight - (c.percentChange - changeMin) / changeRange * innerHeight}
                    <circle cx={x} cy={y} r="3" class={userFills[idx]} />
                  {/each}
                {/if}
              {/each}

              <!-- Y-axis labels (percentage change) -->
              <text x={padding.left - 8} y={padding.top} text-anchor="end" dominant-baseline="middle" class="fill-gray-400 text-[9px]">
                {changeMax > 0 ? '+' : ''}{changeMax.toFixed(1)}%
              </text>
              <text x={padding.left - 8} y={zeroLineY} text-anchor="end" dominant-baseline="middle" class="fill-gray-500 text-[9px] font-medium">
                0%
              </text>
              <text x={padding.left - 8} y={padding.top + innerHeight} text-anchor="end" dominant-baseline="middle" class="fill-gray-400 text-[9px]">
                {changeMin.toFixed(1)}%
              </text>
            </svg>
          </div>

          <!-- Legend with starting weights -->
          <div class="flex items-center justify-center gap-6 mt-4 text-xs text-gray-500">
            {#each userData as { user }, idx}
              <div class="flex items-center gap-2">
                <div class={clsx('w-4 h-0.5 rounded', idx === 0 ? 'bg-primary-500' : idx === 1 ? 'bg-accent-500' : 'bg-cardio-500')}></div>
                <span>{user.name}</span>
                {#if normalizedWeightData[idx]?.startWeight}
                  <span class="text-gray-400">
                    (start: {weightFromMetric(normalizedWeightData[idx].startWeight, $settings.weight_unit).toFixed(1)})
                  </span>
                {/if}
              </div>
            {/each}
          </div>
          <p class="text-center text-xs text-gray-400 mt-2">Chart shows % change from each person's starting weight</p>
        {:else}
          <div class="h-48 flex items-center justify-center text-gray-400">
            <p>No weight data yet</p>
          </div>
        {/if}
      </div>

      <!-- Activities Grid - Last 5 Days Side by Side -->
      <div class="card p-6">
        <div class="flex items-center gap-2 mb-4">
          <Activity size={20} class="text-cardio-500" />
          <h2 class="text-lg font-semibold">Activities</h2>
          <span class="text-xs text-gray-400 ml-auto">Last 5 days</span>
        </div>

        {#if userData.length >= 2}
          <!-- Header row with user names -->
          <div class="grid grid-cols-[1fr_1fr_1fr] gap-2 mb-3 text-sm font-medium">
            <div></div>
            <div class="text-center text-primary-500">{userData[0].user.name}</div>
            <div class="text-center text-accent-500">{userData[1].user.name}</div>
          </div>

          <!-- Day rows -->
          <div class="space-y-2">
            {#each last5Days as day}
              {@const myActivities = activitiesByUserAndDate[0]?.byDate[day.date] || []}
              {@const partnerActivities = activitiesByUserAndDate[1]?.byDate[day.date] || []}
              <div class="grid grid-cols-[1fr_1fr_1fr] gap-2 items-center py-2 px-3 rounded-lg bg-gray-50 dark:bg-gray-700/50">
                <!-- Date -->
                <div class="text-xs text-gray-500">{day.display}</div>

                <!-- My activities -->
                <div class="flex flex-wrap justify-center gap-1">
                  {#if myActivities.length > 0}
                    {#each myActivities as activity}
                      {@const IconComponent = getActivityIcon(activity.icon)}
                      <div
                        class={clsx(
                          'p-1.5 rounded-full',
                          activity.activity_type === 'cardio'
                            ? 'bg-cardio-100 dark:bg-cardio-900/30'
                            : 'bg-strength-100 dark:bg-strength-900/30'
                        )}
                        title="{activity.name}{activity.duration_mins ? ` · ${activity.duration_mins} min` : ''}"
                      >
                        <svelte:component
                          this={IconComponent}
                          size={14}
                          class={clsx(
                            activity.activity_type === 'cardio'
                              ? 'text-cardio-500'
                              : 'text-strength-500'
                          )}
                        />
                      </div>
                    {/each}
                  {:else}
                    <span class="text-gray-300 dark:text-gray-600">—</span>
                  {/if}
                </div>

                <!-- Partner activities -->
                <div class="flex flex-wrap justify-center gap-1">
                  {#if partnerActivities.length > 0}
                    {#each partnerActivities as activity}
                      {@const IconComponent = getActivityIcon(activity.icon)}
                      <div
                        class={clsx(
                          'p-1.5 rounded-full',
                          activity.activity_type === 'cardio'
                            ? 'bg-cardio-100 dark:bg-cardio-900/30'
                            : 'bg-strength-100 dark:bg-strength-900/30'
                        )}
                        title="{activity.name}{activity.duration_mins ? ` · ${activity.duration_mins} min` : ''}"
                      >
                        <svelte:component
                          this={IconComponent}
                          size={14}
                          class={clsx(
                            activity.activity_type === 'cardio'
                              ? 'text-cardio-500'
                              : 'text-strength-500'
                          )}
                        />
                      </div>
                    {/each}
                  {:else}
                    <span class="text-gray-300 dark:text-gray-600">—</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>

          <!-- Legend -->
          <div class="flex items-center justify-center flex-wrap gap-3 mt-4 text-xs text-gray-400">
            {#each LEGEND_ICONS.slice(0, 4) as { icon: IconComponent, label }}
              <div class="flex items-center gap-1">
                <svelte:component this={IconComponent} size={12} class="text-gray-500" />
                <span>{label}</span>
              </div>
            {/each}
          </div>
        {:else}
          <div class="h-48 flex items-center justify-center text-gray-400">
            <p>No activity data yet</p>
          </div>
        {/if}
      </div>
    </div>
  {/if}
  {/if}
</div>
