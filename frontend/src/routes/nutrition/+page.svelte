<script lang="ts">
  import { onMount } from 'svelte';
  import { format } from 'date-fns';
  import { Plus, Trash2, Copy } from 'lucide-svelte';
  import { api, type Meal, type MealInput } from '$lib/api/client';

  const MEAL_LABELS = ['Breakfast', 'Lunch', 'Dinner', 'Snack'];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let meals: Meal[] = [];
  let showForm = false;
  let loading = true;

  async function loadMeals() {
    loading = true;
    try {
      meals = await api.getMeals(selectedDate);
    } catch (err) {
      console.error('Failed to load meals:', err);
    } finally {
      loading = false;
    }
  }

  onMount(loadMeals);

  $: totalCalories = meals.reduce((sum, m) => sum + (m.calories || 0), 0);

  async function handleSubmit(e: SubmitEvent) {
    const formData = new FormData(e.target as HTMLFormElement);
    const data: MealInput = {
      date: selectedDate,
      label: formData.get('label') as string,
      time: formData.get('time') as string,
      calories: parseInt(formData.get('calories') as string) || undefined,
      description: formData.get('description') as string,
    };

    try {
      await api.createMeal(data);
      showForm = false;
      loadMeals();
    } catch (err) {
      console.error('Failed to create meal:', err);
    }
  }

  async function deleteMeal(id: number) {
    try {
      await api.deleteMeal(id);
      loadMeals();
    } catch (err) {
      console.error('Failed to delete meal:', err);
    }
  }

  async function copyYesterday() {
    try {
      await api.copyMealsFromYesterday(selectedDate);
      loadMeals();
    } catch (err) {
      console.error('Failed to copy meals:', err);
    }
  }

  function handleDateChange(e: Event) {
    selectedDate = (e.target as HTMLInputElement).value;
    loadMeals();
  }
</script>

<svelte:head>
  <title>Nutrition - Askesis</title>
</svelte:head>

<div>
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Nutrition</h1>
    <div class="flex items-center gap-4">
      <button
        on:click={copyYesterday}
        class="flex items-center gap-2 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
      >
        <Copy size={16} />
        Copy yesterday
      </button>
      <input
        type="date"
        value={selectedDate}
        on:change={handleDateChange}
        class="input max-w-[180px]"
      />
    </div>
  </div>

  <!-- Summary -->
  <div class="card p-4 mb-6">
    <p class="text-sm text-gray-500">Total calories</p>
    <p class="text-3xl font-bold">{totalCalories}</p>
  </div>

  <!-- Meals list -->
  <div class="card p-6 mb-6">
    {#if loading}
      <div class="flex items-center justify-center py-8">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
      </div>
    {:else if meals.length > 0}
      <ul class="space-y-4">
        {#each meals as meal}
          <li class="flex items-start justify-between py-3 border-b border-gray-100 dark:border-gray-700 last:border-0">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-xs px-2 py-1 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400">
                  {meal.label}
                </span>
                {#if meal.time}
                  <span class="text-sm text-gray-500">{meal.time}</span>
                {/if}
              </div>
              {#if meal.description}
                <p class="mt-1 text-gray-600 dark:text-gray-400">{meal.description}</p>
              {/if}
            </div>
            <div class="flex items-center gap-4">
              {#if meal.calories}
                <span class="font-medium">{meal.calories} cal</span>
              {/if}
              <button
                on:click={() => deleteMeal(meal.id)}
                class="text-gray-400 hover:text-red-500"
              >
                <Trash2 size={18} />
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="text-gray-500 text-center py-4">No meals logged</p>
    {/if}
  </div>

  <!-- Add meal form -->
  {#if showForm}
    <form on:submit|preventDefault={handleSubmit} class="card p-6">
      <h2 class="text-lg font-semibold mb-4">Add Meal</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="label">Label</label>
          <select name="label" class="input">
            {#each MEAL_LABELS as label}
              <option value={label}>{label}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="label">Time</label>
          <input type="time" name="time" class="input" />
        </div>
        <div>
          <label class="label">Calories</label>
          <input type="number" name="calories" class="input" />
        </div>
        <div>
          <label class="label">Description</label>
          <input type="text" name="description" class="input" />
        </div>
      </div>
      <div class="mt-4 flex justify-end gap-3">
        <button type="button" on:click={() => (showForm = false)} class="btn-secondary">
          Cancel
        </button>
        <button type="submit" class="btn-primary">Add</button>
      </div>
    </form>
  {:else}
    <button
      on:click={() => (showForm = true)}
      class="flex items-center gap-2 px-4 py-3 w-full border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl text-gray-500 hover:border-primary-500 hover:text-primary-500"
    >
      <Plus size={20} />
      Add meal
    </button>
  {/if}
</div>
