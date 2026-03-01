<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Plus, Trash2, Activity, Dumbbell, ChevronDown, ChevronUp, ChevronLeft, ChevronRight } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type Activity as ActivityType, type ActivityInput } from '$lib/api/client';

  const ACTIVITY_TAGS = ['Commute', 'Training', 'Race', 'Social', 'Fun', 'Weekend'];

  const TAG_COLORS: Record<string, string> = {
    Commute: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    Training: 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400',
    Race: 'bg-accent-100 text-accent-700 dark:bg-accent-900/30 dark:text-accent-400',
    Social: 'bg-nutrition-100 text-nutrition-700 dark:bg-nutrition-900/30 dark:text-nutrition-400',
    Fun: 'bg-rest-100 text-rest-700 dark:bg-rest-900/30 dark:text-rest-400',
    Weekend: 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400',
  };

  let activities: ActivityType[] = [];
  let showForm = false;
  let selectedTags: string[] = [];
  let loading = true;
  let expandedActivity: number | null = null;
  let selectedDate = format(new Date(), 'yyyy-MM-dd');

  async function loadActivities() {
    loading = true;
    try {
      activities = await api.getActivities(selectedDate, selectedDate);
    } catch (err) {
      console.error('Failed to load activities:', err);
    } finally {
      loading = false;
    }
  }

  onMount(loadActivities);

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
    const data: ActivityInput = {
      date: formData.get('date') as string,
      name: formData.get('name') as string,
      activity_type: formData.get('activity_type') as 'cardio' | 'strength',
      duration_mins: parseInt(formData.get('duration_mins') as string) || undefined,
      calories: parseInt(formData.get('calories') as string) || undefined,
      distance_km: parseFloat(formData.get('distance_km') as string) || undefined,
      notes: formData.get('notes') as string,
      tags: selectedTags.join(','),
      exercises: [],
    };

    try {
      await api.createActivity(data);
      showForm = false;
      selectedTags = [];
      loadActivities();
    } catch (err) {
      console.error('Failed to create activity:', err);
    }
  }

  async function deleteActivity(id: number) {
    try {
      await api.deleteActivity(id);
      loadActivities();
    } catch (err) {
      console.error('Failed to delete activity:', err);
    }
  }
</script>

<svelte:head>
  <title>Activities - Askesis</title>
</svelte:head>

<div>
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold">Activities</h1>
      <p class="text-gray-500 text-sm mt-1">Track your workouts and exercises</p>
    </div>
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2">
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
          class="input max-w-[180px]"
        />
        <button
          type="button"
          on:click={nextDay}
          class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
        >
          <ChevronRight size={20} />
        </button>
      </div>
      <button on:click={() => (showForm = !showForm)} class="btn-primary flex items-center gap-2">
        <Plus size={20} />
        Add Activity
      </button>
    </div>
  </div>

  <!-- Add activity form -->
  {#if showForm}
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
          <label for="duration" class="label">Duration (mins)</label>
          <input id="duration" type="number" name="duration_mins" placeholder="30" class="input" />
        </div>
        <div>
          <label for="calories" class="label">Calories</label>
          <input id="calories" type="number" name="calories" placeholder="250" class="input" />
        </div>
        <div>
          <label for="distance" class="label">Distance (km)</label>
          <input id="distance" type="number" name="distance_km" step="0.1" placeholder="5.0" class="input" />
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
        <button type="button" on:click={() => { showForm = false; selectedTags = []; }} class="btn-secondary">
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
                  <div class="flex items-center gap-2 mb-1">
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
                    {#if hasExercises}
                      <span class="text-xs text-gray-400">
                        ({activity.exercises.length} exercises)
                      </span>
                    {/if}
                  </div>
                  <p class="text-sm text-gray-500">
                    {format(new Date(activity.date), 'MMM d, yyyy')}
                    {#if activity.duration_mins} · {activity.duration_mins} min{/if}
                    {#if activity.distance_km} · {activity.distance_km} km{/if}
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
                            <th class="pb-2 font-medium text-center">Weight (kg)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {#each activity.exercises as exercise}
                            <tr class="border-b border-gray-100 dark:border-gray-700 last:border-0">
                              <td class="py-2 font-medium">{exercise.name}</td>
                              <td class="py-2 text-center">{exercise.sets || '-'}</td>
                              <td class="py-2 text-center font-mono text-xs">{exercise.reps || '-'}</td>
                              <td class="py-2 text-center">{exercise.weight_kg || '-'}</td>
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
                <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-600 flex justify-end">
                  <button
                    on:click|stopPropagation={() => deleteActivity(activity.id)}
                    class="flex items-center gap-2 px-3 py-1.5 text-sm text-accent-600 hover:bg-accent-50 dark:hover:bg-accent-900/20 rounded-lg transition-colors"
                  >
                    <Trash2 size={16} />
                    Delete
                  </button>
                </div>
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
</div>
