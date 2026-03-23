<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Plus, Trash2, Copy, ChevronLeft, ChevronRight, Camera, Sparkles, X, Image, Upload, Flame, Beef, Wheat, Droplet, Pencil, Check, UtensilsCrossed, ChevronDown, ChevronUp } from 'lucide-svelte';
  import ImportModal from '$lib/components/ImportModal.svelte';
  import FoodSearch from '$lib/components/FoodSearch.svelte';
  import FoodItemForm from '$lib/components/FoodItemForm.svelte';
  import { clsx } from 'clsx';
  import { api, type Meal, type MealInput, type FoodAnalysis, type DailyNutrition, type FoodItem, type MealFoodItemInput } from '$lib/api/client';
  import { offlineApi } from '$lib/stores/data';


  const MEAL_LABELS = ['Breakfast', 'Lunch', 'Dinner', 'Snack'];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let meals: Meal[] = [];
  let dailyNutrition: DailyNutrition | null = null;
  let showForm = false;
  let showImportModal = false;
  let loading = true;
  let uploadingMealId: number | null = null;
  let analyzingPhoto = false;
  let photoAnalysis: FoodAnalysis | null = null;
  let photoPreview: string | null = null;
  let selectedFile: File | null = null;

  // File input refs
  let mealPhotoInputs: Record<number, HTMLInputElement | null> = {};
  let newMealPhotoInput: HTMLInputElement | null = null;

  // Edit meal state
  let editingMealId: number | null = null;
  let editMealData: MealInput = { date: '', label: '' };
  let savingMeal = false;

  // Food items for new meal form
  let selectedFoodItems: { food: FoodItem; quantity: number; notes?: string }[] = [];
  let newMealFoodItems: MealFoodItemInput[] = [];
  let showFoodItemForm = false;
  let foodItemInitialName = '';
  let expandedMealId: number | null = null;

  // Editable macro fields (protein, carbs, fat - calories come from meals)
  let editingMacros = false;
  let macroProtein: number | undefined;
  let macroCarbs: number | undefined;
  let macroFat: number | undefined;
  let savingMacros = false;

  async function loadMeals() {
    loading = true;
    try {
      meals = await offlineApi.getMeals(selectedDate, undefined);
    } catch (err) {
      console.error('Failed to load meals:', err);
    } finally {
      loading = false;
    }
  }

  async function loadDailyNutrition() {
    try {
      dailyNutrition = await offlineApi.getDailyNutrition(selectedDate, undefined);
      // Populate macro fields from daily nutrition
      macroProtein = dailyNutrition.protein_g ?? undefined;
      macroCarbs = dailyNutrition.carbs_g ?? undefined;
      macroFat = dailyNutrition.fat_g ?? undefined;
    } catch {
      dailyNutrition = null;
      macroProtein = undefined;
      macroCarbs = undefined;
      macroFat = undefined;
    }
  }

  async function saveMacros() {
    savingMacros = true;
    try {
      await offlineApi.saveDailyNutrition({
        date: selectedDate,
        protein_g: macroProtein,
        carbs_g: macroCarbs,
        fat_g: macroFat,
      });
      editingMacros = false;
      await loadDailyNutrition();
    } catch (err) {
      console.error('Failed to save macros:', err);
    } finally {
      savingMacros = false;
    }
  }

  async function loadData() {
    await Promise.all([loadMeals(), loadDailyNutrition()]);
  }

  onMount(loadData);

  $: totalCalories = meals.reduce((sum, m) => sum + (m.calories || 0), 0);

  async function handleSubmit(e: SubmitEvent) {
    const formData = new FormData(e.target as HTMLFormElement);
    const timeValue = formData.get('time') as string;
    const data: MealInput = {
      date: selectedDate,
      label: formData.get('label') as string,
      time: timeValue || undefined,  // Convert empty string to undefined
      calories: parseInt(formData.get('calories') as string) || photoAnalysis?.calories || undefined,
      description: formData.get('description') as string || photoAnalysis?.description || undefined,
      food_items: newMealFoodItems.length > 0 ? newMealFoodItems : undefined,
    };

    try {
      const meal = await offlineApi.createMeal(data);

      // Upload photo if selected
      if (selectedFile) {
        await api.uploadMealPhoto(meal.id, selectedFile, true);
      }

      showForm = false;
      clearPhotoPreview();
      selectedFoodItems = [];
      newMealFoodItems = [];
      loadMeals();
    } catch (err) {
      console.error('Failed to create meal:', err);
    }
  }

  async function deleteMeal(id: number) {
    try {
      await offlineApi.deleteMeal(id);
      loadMeals();
    } catch (err) {
      console.error('Failed to delete meal:', err);
    }
  }

  function startEditMeal(meal: Meal) {
    editingMealId = meal.id;
    editMealData = {
      date: meal.date,
      label: meal.label,
      time: meal.time || undefined,
      calories: meal.calories || undefined,
      description: meal.description || undefined,
      food_items: meal.food_items?.map(fi => ({
        food_item_id: fi.food_item_id,
        quantity: fi.quantity,
        notes: fi.notes,
      })),
    };
  }

  function cancelEditMeal() {
    editingMealId = null;
    editMealData = { date: '', label: '' };
  }

  async function saveEditMeal() {
    if (!editingMealId) return;
    savingMeal = true;
    try {
      await offlineApi.updateMeal(editingMealId, editMealData);
      editingMealId = null;
      editMealData = { date: '', label: '' };
      loadMeals();
    } catch (err) {
      console.error('Failed to update meal:', err);
    } finally {
      savingMeal = false;
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
    loadData();
  }

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadData();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadData();
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
  <!-- Header -->
  <div class="mb-6">
    <h1 class="text-2xl font-bold">Nutrition</h1>
    <p class="text-gray-500 text-sm mt-1">Track your meals and calories</p>

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
      <button
          on:click={copyYesterday}
          class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          title="Copy yesterday's meals"
        >
          <Copy size={16} />
        </button>
    </div>
  </div>

  <!-- Daily Nutrition Summary -->
  <div class="card p-4 mb-6">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-medium text-gray-500">Daily Totals</h3>
      {#if editingMacros}
          <button
            on:click={saveMacros}
            disabled={savingMacros}
            class="p-1.5 text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/30 rounded"
            title="Save macros"
          >
            <Check size={16} />
          </button>
        {:else}
          <button
            on:click={() => editingMacros = true}
            class="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            title="Edit macros"
          >
            <Pencil size={16} />
          </button>
        {/if}
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <!-- Calories - always from meals, not editable -->
      <div>
        <p class="text-sm text-gray-500 flex items-center gap-1">
          <Flame size={14} class="text-nutrition-500" />
          Calories
        </p>
        <p class="text-2xl font-bold">{totalCalories || '—'}</p>
        <p class="text-xs text-gray-400">from meals</p>
      </div>

      <!-- Protein - editable -->
      <div>
        <p class="text-sm text-gray-500 flex items-center gap-1">
          <Beef size={14} class="text-strength-500" />
          Protein
        </p>
        {#if editingMacros}
          <input
            type="number"
            step="0.1"
            bind:value={macroProtein}
            placeholder="—"
            class="input text-lg font-bold w-full mt-1"
          />
        {:else}
          <p class="text-2xl font-bold">
            {macroProtein ?? '—'}{#if macroProtein}<span class="text-sm font-normal text-gray-400">g</span>{/if}
          </p>
        {/if}
      </div>

      <!-- Carbs - editable -->
      <div>
        <p class="text-sm text-gray-500 flex items-center gap-1">
          <Wheat size={14} class="text-cardio-500" />
          Carbs
        </p>
        {#if editingMacros}
          <input
            type="number"
            step="0.1"
            bind:value={macroCarbs}
            placeholder="—"
            class="input text-lg font-bold w-full mt-1"
          />
        {:else}
          <p class="text-2xl font-bold">
            {macroCarbs ?? '—'}{#if macroCarbs}<span class="text-sm font-normal text-gray-400">g</span>{/if}
          </p>
        {/if}
      </div>

      <!-- Fat - editable -->
      <div>
        <p class="text-sm text-gray-500 flex items-center gap-1">
          <Droplet size={14} class="text-nutrition-600" />
          Fat
        </p>
        {#if editingMacros}
          <input
            type="number"
            step="0.1"
            bind:value={macroFat}
            placeholder="—"
            class="input text-lg font-bold w-full mt-1"
          />
        {:else}
          <p class="text-2xl font-bold">
            {macroFat ?? '—'}{#if macroFat}<span class="text-sm font-normal text-gray-400">g</span>{/if}
          </p>
        {/if}
      </div>
    </div>
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
          <li class="py-3 border-b border-gray-100 dark:border-gray-700 last:border-0">
            {#if editingMealId === meal.id}
              <!-- Edit mode -->
              <div class="space-y-3">
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <label class="label text-xs">Label</label>
                    <select bind:value={editMealData.label} class="input text-sm">
                      {#each MEAL_LABELS as label}
                        <option value={label}>{label}</option>
                      {/each}
                    </select>
                  </div>
                  <div>
                    <label class="label text-xs">Time</label>
                    <input type="time" bind:value={editMealData.time} class="input text-sm" />
                  </div>
                  <div>
                    <label class="label text-xs">Calories</label>
                    <input type="number" bind:value={editMealData.calories} class="input text-sm" />
                  </div>
                  <div>
                    <label class="label text-xs">Description</label>
                    <input type="text" bind:value={editMealData.description} class="input text-sm" />
                  </div>
                </div>
                <div class="flex justify-end gap-2">
                  <button on:click={cancelEditMeal} class="btn-secondary text-sm px-3 py-1">
                    Cancel
                  </button>
                  <button on:click={saveEditMeal} disabled={savingMeal} class="btn-primary text-sm px-3 py-1">
                    {savingMeal ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </div>
            {:else}
              <!-- View mode -->
              <div class="flex items-start gap-4">
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
                    <span class="text-xs px-2 py-1 rounded-full bg-primary-100 dark:bg-gray-700 text-primary-700 dark:text-primary-400">
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
                  {#if meal.food_items && meal.food_items.length > 0}
                    <button
                      type="button"
                      on:click={() => expandedMealId = expandedMealId === meal.id ? null : meal.id}
                      class="mt-1 text-xs text-primary-500 hover:underline flex items-center gap-1"
                    >
                      <UtensilsCrossed size={12} />
                      {meal.food_items.length} food item{meal.food_items.length !== 1 ? 's' : ''}
                      {#if expandedMealId === meal.id}<ChevronUp size={12} />{:else}<ChevronDown size={12} />{/if}
                    </button>
                    {#if expandedMealId === meal.id}
                      <div class="mt-2 space-y-1">
                        {#each meal.food_items as fi}
                          <div class="text-xs text-gray-500 flex justify-between px-2 py-1 bg-gray-50 dark:bg-gray-800 rounded">
                            <span>{fi.food_item_name} <span class="text-gray-400">x{fi.quantity}</span></span>
                            <span>{fi.calories ? `${fi.calories} cal` : ''}</span>
                          </div>
                        {/each}
                      </div>
                    {/if}
                  {/if}
                </div>

                <div class="flex items-center gap-3 flex-shrink-0">
                  {#if meal.calories}
                    <span class="font-medium">{meal.calories} cal</span>
                  {/if}
                    <button
                      on:click={() => startEditMeal(meal)}
                      class="text-gray-400 hover:text-primary-500"
                      title="Edit meal"
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      on:click={() => deleteMeal(meal.id)}
                      class="text-gray-400 hover:text-red-500"
                      title="Delete meal"
                    >
                      <Trash2 size={18} />
                    </button>
                </div>
              </div>
            {/if}
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

      <!-- Food items section -->
      <div class="mb-4">
        <span class="label flex items-center gap-2">
          <UtensilsCrossed size={16} class="text-nutrition-500" />
          Food Items
          <span class="text-xs text-gray-400 font-normal">(optional)</span>
          <a href="/nutrition/foods" class="text-xs text-primary-500 hover:underline ml-auto font-normal">Manage foods</a>
        </span>
        <div class="mt-2">
          <FoodSearch
            bind:selectedFoods={selectedFoodItems}
            on:change={(e) => { newMealFoodItems = e.detail; }}
            on:createNew={(e) => { foodItemInitialName = e.detail; showFoodItemForm = true; }}
          />
        </div>
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
          <label class="label">
            Calories
            {#if newMealFoodItems.length > 0}
              <span class="text-xs text-gray-400">(auto-calculated if empty)</span>
            {:else if photoAnalysis?.calories}
              <span class="text-xs text-accent-500">(AI: {photoAnalysis.calories})</span>
            {/if}
          </label>
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
        <button type="button" on:click={() => { showForm = false; clearPhotoPreview(); selectedFoodItems = []; newMealFoodItems = []; }} class="btn-secondary">
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

  <!-- Import Button -->
    <div class="mt-6">
      <button
        on:click={() => (showImportModal = true)}
        class="btn-secondary w-full flex items-center justify-center gap-2"
      >
        <Upload size={20} />
        Import Bulk
      </button>
    </div>
</div>

<ImportModal
  bind:show={showImportModal}
  dataType="meals"
  title="Import Meals"
  on:success={() => loadData()}
/>

<FoodItemForm
  bind:show={showFoodItemForm}
  initialName={foodItemInitialName}
  on:saved={(e) => {
    // Add newly created food to the selection
    const food = e.detail;
    selectedFoodItems = [...selectedFoodItems, { food, quantity: 1 }];
    newMealFoodItems = [...newMealFoodItems, { food_item_id: food.id, quantity: 1 }];
  }}
/>
