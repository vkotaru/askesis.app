<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Plus, Trash2, Copy, ChevronLeft, ChevronRight, Camera, Sparkles, X, Image } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type Meal, type MealInput, type FoodAnalysis } from '$lib/api/client';

  const MEAL_LABELS = ['Breakfast', 'Lunch', 'Dinner', 'Snack'];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let meals: Meal[] = [];
  let showForm = false;
  let loading = true;
  let uploadingMealId: number | null = null;
  let analyzingPhoto = false;
  let photoAnalysis: FoodAnalysis | null = null;
  let photoPreview: string | null = null;
  let selectedFile: File | null = null;

  // File input refs
  let mealPhotoInputs: Record<number, HTMLInputElement | null> = {};
  let newMealPhotoInput: HTMLInputElement | null = null;

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
      calories: parseInt(formData.get('calories') as string) || photoAnalysis?.calories || undefined,
      description: formData.get('description') as string || photoAnalysis?.description || undefined,
    };

    try {
      const meal = await api.createMeal(data);

      // Upload photo if selected
      if (selectedFile) {
        await api.uploadMealPhoto(meal.id, selectedFile, true);
      }

      showForm = false;
      clearPhotoPreview();
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

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadMeals();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadMeals();
  }

  async function handleMealPhotoUpload(mealId: number, e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    uploadingMealId = mealId;
    try {
      const result = await api.uploadMealPhoto(mealId, file, true);
      // Update the meal in the list
      meals = meals.map(m => m.id === mealId ? { ...m, ...result } : m);
    } catch (err) {
      console.error('Failed to upload photo:', err);
    } finally {
      uploadingMealId = null;
      input.value = '';
    }
  }

  async function handleNewMealPhoto(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    selectedFile = file;
    photoPreview = URL.createObjectURL(file);

    // Analyze with Gemini
    analyzingPhoto = true;
    try {
      photoAnalysis = await api.analyzeFoodPhoto(file);
    } catch (err) {
      console.error('Failed to analyze photo:', err);
      photoAnalysis = null;
    } finally {
      analyzingPhoto = false;
    }
  }

  function clearPhotoPreview() {
    if (photoPreview) {
      URL.revokeObjectURL(photoPreview);
    }
    photoPreview = null;
    photoAnalysis = null;
    selectedFile = null;
  }

  function triggerMealPhotoUpload(mealId: number) {
    mealPhotoInputs[mealId]?.click();
  }
</script>

<svelte:head>
  <title>Nutrition - Askesis</title>
</svelte:head>

<div>
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold">Nutrition</h1>
      <p class="text-gray-500 text-sm mt-1">Track your meals and calories</p>
    </div>
    <div class="flex items-center gap-2">
      <button
        on:click={copyYesterday}
        class="flex items-center gap-2 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
        title="Copy yesterday's meals"
      >
        <Copy size={16} />
      </button>
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
          <li class="flex items-start gap-4 py-3 border-b border-gray-100 dark:border-gray-700 last:border-0">
            <!-- Photo thumbnail -->
            {#if meal.photo_url}
              <img
                src={api.getMealPhotoUrl(meal.id)}
                alt={meal.label}
                class="w-16 h-16 rounded-lg object-cover flex-shrink-0"
              />
            {:else}
              <button
                on:click={() => triggerMealPhotoUpload(meal.id)}
                disabled={uploadingMealId === meal.id}
                class="w-16 h-16 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center flex-shrink-0 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                title="Add photo"
              >
                {#if uploadingMealId === meal.id}
                  <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-primary-500"></div>
                {:else}
                  <Camera size={20} class="text-gray-400" />
                {/if}
              </button>
            {/if}

            <input
              type="file"
              accept="image/*"
              class="hidden"
              bind:this={mealPhotoInputs[meal.id]}
              on:change={(e) => handleMealPhotoUpload(meal.id, e)}
            />

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs px-2 py-1 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400">
                  {meal.label}
                </span>
                {#if meal.time}
                  <span class="text-sm text-gray-500">{meal.time}</span>
                {/if}
                {#if meal.ai_analysis}
                  <span class="text-xs px-1.5 py-0.5 rounded bg-accent-100 dark:bg-accent-900/30 text-accent-600 dark:text-accent-400 flex items-center gap-1">
                    <Sparkles size={10} />
                    AI
                  </span>
                {/if}
              </div>
              {#if meal.description}
                <p class="mt-1 text-gray-600 dark:text-gray-400 truncate">{meal.description}</p>
              {/if}
            </div>

            <div class="flex items-center gap-4 flex-shrink-0">
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

      <!-- Photo upload section -->
      <div class="mb-6">
        <span class="label flex items-center gap-2">
          <Camera size={16} class="text-nutrition-500" />
          Photo
          <span class="text-xs text-gray-400 font-normal">(optional - AI will analyze)</span>
        </span>

        {#if photoPreview}
          <div class="relative inline-block mt-2">
            <img src={photoPreview} alt="Preview" class="w-32 h-32 object-cover rounded-lg" />
            <button
              type="button"
              on:click={clearPhotoPreview}
              class="absolute -top-2 -right-2 p-1 bg-gray-800 rounded-full text-white hover:bg-gray-700"
            >
              <X size={14} />
            </button>

            {#if analyzingPhoto}
              <div class="absolute inset-0 bg-black/50 rounded-lg flex items-center justify-center">
                <div class="text-center text-white">
                  <Sparkles size={20} class="mx-auto animate-pulse" />
                  <span class="text-xs">Analyzing...</span>
                </div>
              </div>
            {/if}
          </div>

          {#if photoAnalysis}
            <div class="mt-3 p-3 bg-accent-50 dark:bg-accent-900/20 rounded-lg text-sm">
              <div class="flex items-center gap-2 text-accent-600 dark:text-accent-400 font-medium mb-2">
                <Sparkles size={14} />
                AI Analysis
              </div>
              {#if photoAnalysis.calories}
                <p><strong>Estimated:</strong> {photoAnalysis.calories} calories</p>
              {/if}
              {#if photoAnalysis.foods && photoAnalysis.foods.length > 0}
                <p><strong>Foods:</strong> {photoAnalysis.foods.join(', ')}</p>
              {/if}
              {#if photoAnalysis.macros}
                <p class="text-xs text-gray-500 mt-1">
                  Protein: {photoAnalysis.macros.protein_g || 0}g |
                  Carbs: {photoAnalysis.macros.carbs_g || 0}g |
                  Fat: {photoAnalysis.macros.fat_g || 0}g
                </p>
              {/if}
            </div>
          {/if}
        {:else}
          <button
            type="button"
            on:click={() => newMealPhotoInput?.click()}
            class="mt-2 flex items-center gap-2 px-4 py-3 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl text-gray-500 hover:border-nutrition-500 hover:text-nutrition-500 transition-colors"
          >
            <Image size={20} />
            <span>Take or upload a photo</span>
          </button>
        {/if}

        <input
          type="file"
          accept="image/*"
          capture="environment"
          class="hidden"
          bind:this={newMealPhotoInput}
          on:change={handleNewMealPhoto}
        />
      </div>

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
          <label class="label">Calories {#if photoAnalysis?.calories}<span class="text-xs text-accent-500">(AI: {photoAnalysis.calories})</span>{/if}</label>
          <input
            type="number"
            name="calories"
            class="input"
            placeholder={photoAnalysis?.calories?.toString() || ''}
          />
        </div>
        <div>
          <label class="label">Description</label>
          <input
            type="text"
            name="description"
            class="input"
            placeholder={photoAnalysis?.description || ''}
          />
        </div>
      </div>
      <div class="mt-4 flex justify-end gap-3">
        <button type="button" on:click={() => { showForm = false; clearPhotoPreview(); }} class="btn-secondary">
          Cancel
        </button>
        <button type="submit" class="btn-primary" disabled={analyzingPhoto}>
          {#if analyzingPhoto}
            Analyzing...
          {:else}
            Add
          {/if}
        </button>
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
