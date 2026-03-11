<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Plus, Trash2, Activity, Dumbbell, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, ExternalLink, Sun, Sunrise, Sunset, Moon, Upload, History, Calendar } from 'lucide-svelte';
  import ImportModal from '$lib/components/ImportModal.svelte';
  import { clsx } from 'clsx';
  import { api, type Activity as ActivityType, type ActivityInput, type TimeOfDay } from '$lib/api/client';
  import { viewingUserId, isViewingOther } from '$lib/stores/viewContext';
  import { settings } from '$lib/stores/settings';
  import { formatDistance, distanceToMetric, getDistanceLabel, formatWeight, getWeightLabel } from '$lib/utils/units';

  let recentActivities: ActivityType[] = [];

  const ACTIVITY_TAGS = ['Commute', 'Training', 'Race', 'Social', 'Fun', 'Weekend'];

  const TAG_COLORS: Record<string, string> = {
    Commute: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    Training: 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400',
    Race: 'bg-accent-100 text-accent-700 dark:bg-accent-900/30 dark:text-accent-400',
    Social: 'bg-nutrition-100 text-nutrition-700 dark:bg-nutrition-900/30 dark:text-nutrition-400',
    Fun: 'bg-rest-100 text-rest-700 dark:bg-rest-900/30 dark:text-rest-400',
    Weekend: 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400',
  };

  const TIME_OF_DAY_OPTIONS: { value: TimeOfDay; label: string; icon: typeof Sun }[] = [
    { value: 'morning', label: 'Morning', icon: Sunrise },
    { value: 'afternoon', label: 'Afternoon', icon: Sun },
    { value: 'evening', label: 'Evening', icon: Sunset },
    { value: 'night', label: 'Night', icon: Moon },
  ];

  function getPlatformFromUrl(url: string): { name: string; color: string } | null {
    if (url.includes('strava.com')) return { name: 'Strava', color: 'text-orange-500' };
    if (url.includes('hevy.com')) return { name: 'Hevy', color: 'text-blue-500' };
    if (url.includes('garmin.com')) return { name: 'Garmin', color: 'text-cyan-600' };
    return null;
  }

  let activities: ActivityType[] = [];
  let showForm = false;
  let showImportModal = false;
  let selectedTags: string[] = [];
  let selectedTimeOfDay: TimeOfDay | null = null;
  let loading = true;
  let expandedActivity: number | null = null;
  let selectedDate = format(new Date(), 'yyyy-MM-dd');

  async function loadActivities() {
    loading = true;
    try {
      activities = await api.getActivities(selectedDate, selectedDate, $viewingUserId ?? undefined);
    } catch (err) {
      console.error('Failed to load activities:', err);
    } finally {
      loading = false;
    }
  }

  async function loadRecentActivities() {
    try {
      const endDate = format(new Date(), 'yyyy-MM-dd');
      const startDate = format(subDays(new Date(), 60), 'yyyy-MM-dd');
      const allActivities = await api.getActivities(startDate, endDate, $viewingUserId ?? undefined);
      // Sort by date descending and take last 10
      recentActivities = allActivities.sort((a, b) => b.date.localeCompare(a.date)).slice(0, 10);
    } catch {
      recentActivities = [];
    }
  }

  onMount(() => {
    loadActivities();
    loadRecentActivities();
  });

  // Reload when viewing user changes
  $: $viewingUserId, loadActivities();
  $: $viewingUserId, loadRecentActivities();

  function goToDate(date: string) {
    selectedDate = date;
    loadActivities();
  }

  function handleDateChange(e: Event) {
    selectedDate = (e.target as HTMLInputElement).value;
    loadActivities();
  }

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadActivities();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadActivities();
  }

  function toggleTag(tag: string) {
    if (selectedTags.includes(tag)) {
      selectedTags = selectedTags.filter((t) => t !== tag);
    } else {
      selectedTags = [...selectedTags, tag];
    }
  }

  function toggleExpanded(activityId: number) {
    expandedActivity = expandedActivity === activityId ? null : activityId;
  }

  async function handleSubmit(e: SubmitEvent) {
    const formData = new FormData(e.target as HTMLFormElement);
    const urlValue = (formData.get('url') as string)?.trim();
    const distanceInput = parseFloat(formData.get('distance') as string);
    const data: ActivityInput = {
      date: formData.get('date') as string,
      name: formData.get('name') as string,
      activity_type: formData.get('activity_type') as 'cardio' | 'strength',
      time_of_day: selectedTimeOfDay || undefined,
      duration_mins: parseInt(formData.get('duration_mins') as string) || undefined,
      calories: parseInt(formData.get('calories') as string) || undefined,
      distance_km: distanceInput ? distanceToMetric(distanceInput, $settings.distance_unit) : undefined,
      url: urlValue || undefined,
      notes: formData.get('notes') as string,
      tags: selectedTags.join(','),
      exercises: [],
    };

    try {
      await api.createActivity(data);
      showForm = false;
      selectedTags = [];
      selectedTimeOfDay = null;
      loadActivities();
      loadRecentActivities();
    } catch (err) {
      console.error('Failed to create activity:', err);
    }
  }

  async function deleteActivity(id: number) {
    try {
      await api.deleteActivity(id);
      loadActivities();
      loadRecentActivities();
    } catch (err) {
      console.error('Failed to delete activity:', err);
    }
  }
</script>

<svelte:head>
  <title>Activities - Askesis</title>
</svelte:head>

<div>
  <!-- Header -->
  <div class="mb-6">
    <h1 class="text-2xl font-bold">Activities</h1>
    <p class="text-gray-500 text-sm mt-1">Track your workouts and exercises</p>

    <!-- Date Navigation -->
    <div class="flex items-center justify-center gap-2 mt-4">
      <button
        type="button"
        on:click={prevDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronLeft size={20} />
      </button>
      <input
        type="date"
        value={selectedDate}
        on:change={handleDateChange}
        class="input max-w-[180px] text-center"
      />
      <button
        type="button"
        on:click={nextDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronRight size={20} />
      </button>
    </div>

    <!-- Add Activity Button -->
    {#if !$isViewingOther}
      <div class="flex justify-center mt-4">
        <button on:click={() => (showForm = !showForm)} class="btn-primary flex items-center gap-2">
          <Plus size={20} />
          Add Activity
        </button>
      </div>
    {/if}
  </div>

  <!-- Add activity form -->
  {#if showForm && !$isViewingOther}
    <form on:submit|preventDefault={handleSubmit} class="card p-6 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label for="activity-date" class="label">Date</label>
          <input id="activity-date" type="date" name="date" value={selectedDate} class="input" />
        </div>
        <div>
          <label for="activity-name" class="label">Name</label>
          <input id="activity-name" type="text" name="name" required placeholder="Morning Run" class="input" />
        </div>
        <div>
          <label for="activity-type" class="label">Type</label>
          <select id="activity-type" name="activity_type" class="input">
            <option value="cardio">Cardio</option>
            <option value="strength">Strength</option>
          </select>
        </div>
        <div>
          <span class="label">Time of Day</span>
          <div class="flex gap-2">
            {#each TIME_OF_DAY_OPTIONS as tod}
              {@const isSelected = selectedTimeOfDay === tod.value}
              <button
                type="button"
                on:click={() => selectedTimeOfDay = isSelected ? null : tod.value}
                class={clsx(
                  'flex-1 flex flex-col items-center gap-1 p-2 rounded-lg border transition-all',
                  isSelected
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 text-primary-600'
                    : 'border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                )}
              >
                <svelte:component this={tod.icon} size={16} />
                <span class="text-xs">{tod.label}</span>
              </button>
            {/each}
          </div>
        </div>
        <div>
          <label for="duration" class="label">Duration (mins)</label>
          <input id="duration" type="number" name="duration_mins" placeholder="30" class="input" />
        </div>
        <div>
          <label for="calories" class="label">Calories</label>
          <input id="calories" type="number" name="calories" placeholder="250" class="input" />
        </div>
        <div>
          <label for="distance" class="label">Distance ({getDistanceLabel($settings.distance_unit)})</label>
          <input id="distance" type="number" name="distance" step="0.01" placeholder="5.00" class="input" />
        </div>
        <div class="md:col-span-3">
          <label for="url" class="label">External Link (Strava, Hevy, Garmin)</label>
          <input id="url" type="url" name="url" placeholder="https://www.strava.com/activities/..." class="input" />
        </div>
      </div>

      <div class="mt-4">
        <span class="label">Tags</span>
        <div class="flex flex-wrap gap-2">
          {#each ACTIVITY_TAGS as tag}
            {@const isSelected = selectedTags.includes(tag)}
            <button
              type="button"
              on:click={() => toggleTag(tag)}
              class={clsx(
                'px-3 py-1.5 rounded-full text-sm font-medium transition-all',
                isSelected
                  ? TAG_COLORS[tag]
                  : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200'
              )}
            >
              {tag}
            </button>
          {/each}
        </div>
      </div>

      <div class="mt-4">
        <label for="notes" class="label">Notes</label>
        <textarea id="notes" name="notes" rows={2} placeholder="How did it feel?" class="input resize-none"></textarea>
      </div>

      <div class="mt-6 flex justify-end gap-3">
        <button type="button" on:click={() => { showForm = false; selectedTags = []; selectedTimeOfDay = null; }} class="btn-secondary">
          Cancel
        </button>
        <button type="submit" class="btn-primary">Save Activity</button>
      </div>
    </form>
  {/if}

  <!-- Activities list -->
  <div class="card p-6">
    {#if loading}
      <div class="flex items-center justify-center py-8">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
      </div>
    {:else if activities.length > 0}
      <ul class="space-y-3">
        {#each activities as activity}
          {@const isExpanded = expandedActivity === activity.id}
          {@const hasExercises = activity.exercises && activity.exercises.length > 0}
          <li class="rounded-xl bg-gray-50 dark:bg-gray-700/50 overflow-hidden transition-colors">
            <button
              type="button"
              on:click={() => toggleExpanded(activity.id)}
              class="w-full flex items-start justify-between p-4 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-left"
            >
              <div class="flex gap-4">
                <div
                  class={clsx(
                    'p-3 rounded-xl',
                    activity.activity_type === 'cardio'
                      ? 'bg-cardio-100 dark:bg-cardio-900/30'
                      : 'bg-strength-100 dark:bg-strength-900/30'
                  )}
                >
                  {#if activity.activity_type === 'cardio'}
                    <Activity size={24} class="text-cardio-600 dark:text-cardio-400" />
                  {:else}
                    <Dumbbell size={24} class="text-strength-600 dark:text-strength-400" />
                  {/if}
                </div>
                <div>
                  <div class="flex items-center gap-2 mb-1 flex-wrap">
                    <span class="font-semibold">{activity.name}</span>
                    <span
                      class={clsx(
                        'text-xs px-2 py-0.5 rounded-full font-medium',
                        activity.activity_type === 'cardio'
                          ? 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400'
                          : 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400'
                      )}
                    >
                      {activity.activity_type}
                    </span>
                    {#if activity.time_of_day}
                      {@const todOption = TIME_OF_DAY_OPTIONS.find(t => t.value === activity.time_of_day)}
                      {#if todOption}
                        <span class="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 flex items-center gap-1">
                          <svelte:component this={todOption.icon} size={12} />
                          {todOption.label}
                        </span>
                      {/if}
                    {/if}
                    {#if activity.url}
                      {@const platform = getPlatformFromUrl(activity.url)}
                      <a
                        href={activity.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        on:click|stopPropagation
                        class={clsx(
                          'text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 dark:bg-gray-700 flex items-center gap-1 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors',
                          platform?.color || 'text-gray-600 dark:text-gray-400'
                        )}
                      >
                        <ExternalLink size={12} />
                        {platform?.name || 'Link'}
                      </a>
                    {/if}
                    {#if hasExercises}
                      <span class="text-xs text-gray-400">
                        ({activity.exercises.length} exercises)
                      </span>
                    {/if}
                  </div>
                  <p class="text-sm text-gray-500">
                    {format(new Date(activity.date), 'MMM d, yyyy')}
                    {#if activity.duration_mins} · {activity.duration_mins} min{/if}
                    {#if activity.distance_km} · {formatDistance(activity.distance_km, $settings.distance_unit)}{/if}
                    {#if activity.calories} · {activity.calories} cal{/if}
                  </p>
                  {#if activity.tags}
                    <div class="flex gap-1 mt-2">
                      {#each activity.tags.split(',') as tag}
                        <span class={clsx('text-xs px-2 py-0.5 rounded-full', TAG_COLORS[tag] || 'bg-gray-100 dark:bg-gray-700')}>
                          {tag}
                        </span>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>
              <div class="flex items-center gap-2">
                {#if hasExercises || activity.notes}
                  {#if isExpanded}
                    <ChevronUp size={20} class="text-gray-400" />
                  {:else}
                    <ChevronDown size={20} class="text-gray-400" />
                  {/if}
                {/if}
              </div>
            </button>

            <!-- Expanded content -->
            {#if isExpanded}
              <div class="px-4 pb-4 border-t border-gray-200 dark:border-gray-600">
                <!-- Exercises table -->
                {#if hasExercises}
                  <div class="mt-4">
                    <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Exercises</h4>
                    <div class="overflow-x-auto">
                      <table class="w-full text-sm">
                        <thead>
                          <tr class="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-600">
                            <th class="pb-2 font-medium">Exercise</th>
                            <th class="pb-2 font-medium text-center">Sets</th>
                            <th class="pb-2 font-medium text-center">Reps</th>
                            <th class="pb-2 font-medium text-center">Weight ({getWeightLabel($settings.weight_unit)})</th>
                          </tr>
                        </thead>
                        <tbody>
                          {#each activity.exercises as exercise}
                            <tr class="border-b border-gray-100 dark:border-gray-700 last:border-0">
                              <td class="py-2 font-medium">{exercise.name}</td>
                              <td class="py-2 text-center">{exercise.sets || '-'}</td>
                              <td class="py-2 text-center font-mono text-xs">{exercise.reps || '-'}</td>
                              <td class="py-2 text-center">{exercise.weight_kg ? formatWeight(exercise.weight_kg, $settings.weight_unit) : '-'}</td>
                            </tr>
                          {/each}
                        </tbody>
                      </table>
                    </div>
                  </div>
                {/if}

                <!-- Notes -->
                {#if activity.notes}
                  <div class="mt-4">
                    <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Notes</h4>
                    <p class="text-sm text-gray-600 dark:text-gray-400">{activity.notes}</p>
                  </div>
                {/if}

                <!-- Delete button -->
                {#if !$isViewingOther}
                  <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-600 flex justify-end">
                    <button
                      on:click|stopPropagation={() => deleteActivity(activity.id)}
                      class="flex items-center gap-2 px-3 py-1.5 text-sm text-accent-600 hover:bg-accent-50 dark:hover:bg-accent-900/20 rounded-lg transition-colors"
                    >
                      <Trash2 size={16} />
                      Delete
                    </button>
                  </div>
                {/if}
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <div class="text-center py-12">
        <Activity size={48} class="mx-auto text-gray-300 dark:text-gray-600 mb-4" />
        <p class="text-gray-500">No activities logged yet</p>
        <p class="text-sm text-gray-400 mt-1">Start tracking your workouts!</p>
      </div>
    {/if}
  </div>

<!-- Import Button -->
  {#if !$isViewingOther}
    <div class="mt-6">
      <button
        on:click={() => (showImportModal = true)}
        class="btn-secondary w-full flex items-center justify-center gap-2"
      >
        <Upload size={20} />
        Import Bulk
      </button>
    </div>
  {/if}

<!-- Recent Activities -->
  {#if recentActivities.length > 0}
    <div class="card p-6 mt-6">
      <div class="flex items-center gap-2 mb-4">
        <History size={20} class="text-primary-500" />
        <h2 class="text-lg font-semibold">Recent Activities</h2>
        <span class="text-sm text-gray-400 ml-auto">Last 10 entries</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-gray-200 dark:border-gray-700">
              <th class="pb-3 font-medium text-gray-500">Date</th>
              <th class="pb-3 font-medium text-gray-500">Activity</th>
              <th class="pb-3 font-medium text-gray-500">Type</th>
              <th class="pb-3 font-medium text-gray-500">Duration</th>
              <th class="pb-3 font-medium text-gray-500">Distance</th>
              <th class="pb-3 font-medium text-gray-500">Calories</th>
            </tr>
          </thead>
          <tbody>
            {#each recentActivities as activity}
              <tr
                class={clsx(
                  'border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors',
                  activity.date === selectedDate && 'bg-primary-50 dark:bg-primary-900/20'
                )}
                on:click={() => goToDate(activity.date)}
              >
                <td class="py-3">
                  <div class="flex items-center gap-2">
                    <Calendar size={14} class="text-gray-400" />
                    <span class="font-medium">{format(parseISO(activity.date), 'MMM d')}</span>
                    <span class="text-gray-400 text-xs">{format(parseISO(activity.date), 'EEE')}</span>
                  </div>
                </td>
                <td class="py-3">
                  <span class="font-medium">{activity.name}</span>
                  {#if activity.tags}
                    <div class="flex gap-1 mt-1">
                      {#each activity.tags.split(',').slice(0, 2) as tag}
                        <span class={clsx('text-xs px-1.5 py-0.5 rounded', TAG_COLORS[tag] || 'bg-gray-100 dark:bg-gray-700')}>
                          {tag}
                        </span>
                      {/each}
                    </div>
                  {/if}
                </td>
                <td class="py-3">
                  <span
                    class={clsx(
                      'text-xs px-2 py-0.5 rounded-full font-medium',
                      activity.activity_type === 'cardio'
                        ? 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400'
                        : 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400'
                    )}
                  >
                    {activity.activity_type}
                  </span>
                </td>
                <td class="py-3">
                  {#if activity.duration_mins}
                    {activity.duration_mins} min
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if activity.distance_km}
                    {formatDistance(activity.distance_km, $settings.distance_unit)}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if activity.calories}
                    {activity.calories} cal
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>

<ImportModal
  bind:show={showImportModal}
  dataType="activities"
  title="Import Activities"
  on:success={() => { loadActivities(); loadRecentActivities(); }}
/>
