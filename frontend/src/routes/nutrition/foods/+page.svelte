<script lang="ts">
  import { onMount } from 'svelte';
  import { Search, Plus, Pencil, Trash2, ChevronLeft, ChevronDown, ChevronUp, Minus, Globe, Download } from 'lucide-svelte';
  import FoodItemForm from '$lib/components/FoodItemForm.svelte';
  import { api, type FoodItem, type ExternalFoodResult } from '$lib/api/client';

  const CATEGORIES = [
    '', 'Fruit', 'Vegetable', 'Grain', 'Dairy', 'Meat', 'Seafood',
    'Legume', 'Nut', 'Beverage', 'Snack', 'Condiment', 'Other'
  ];

  let foods: FoodItem[] = [];
  let loading = true;
  let searchQuery = '';
  let selectedCategory = '';
  let userOnly = false;
  let showForm = false;
  let editingFood: FoodItem | null = null;
  let deleteError = '';
  let externalResults: ExternalFoodResult[] = [];
  let searchingExternal = false;
  let importingId: string | null = null;
  let expandedFoodId: number | null = null;
  let previewQty = 1;
  let previewUnit = '';

  // Common unit conversions (approximate, relative to grams)
  const unitToGrams: Record<string, number> = {
    'g': 1, 'kg': 1000, 'oz': 28.35, 'lb': 453.6,
    'ml': 1, 'l': 1000, 'fl oz': 29.57,
    'cup': 240, 'tbsp': 15, 'tsp': 5,
    'piece': 1, 'slice': 1, 'serving': 1,
  };

  // Units that can convert between each other
  const unitGroups: Record<string, string[]> = {
    'g': ['g', '100g', 'kg', 'oz', 'cup', 'tbsp', 'tsp'],
    'ml': ['ml', '100ml', 'l', 'fl oz', 'cup', 'tbsp', 'tsp'],
    'kg': ['g', '100g', 'kg', 'oz'],
    'oz': ['g', '100g', 'oz', 'cup'],
    'cup': ['cup', 'g', '100g', 'tbsp', 'tsp', 'ml'],
    'tbsp': ['tbsp', 'tsp', 'g', 'cup', 'ml'],
    'tsp': ['tsp', 'tbsp', 'g', 'cup', 'ml'],
    'l': ['ml', '100ml', 'l', 'cup'],
    'fl oz': ['fl oz', 'ml', 'cup'],
    'piece': ['piece'],
    'slice': ['slice'],
    'serving': ['serving'],
  };

  function getAvailableUnits(baseUnit: string): string[] {
    return unitGroups[baseUnit] || [baseUnit];
  }

  function getConversionFactor(food: FoodItem, targetUnit: string): number {
    const base = food.serving_unit;
    if (targetUnit === base) return 1;

    // Handle "100g" / "100ml" as special cases
    if (targetUnit === '100g') {
      const baseGrams = unitToGrams[base] ?? 1;
      return 100 / (food.serving_size * baseGrams);
    }
    if (targetUnit === '100ml') {
      const baseMl = unitToGrams[base] ?? 1;
      return 100 / (food.serving_size * baseMl);
    }

    const baseToGrams = unitToGrams[base] ?? 1;
    const targetToGrams = unitToGrams[targetUnit] ?? 1;

    // Convert: food.serving_size in base unit → grams → target unit
    const gramsPerServing = food.serving_size * baseToGrams;
    const targetPerServing = gramsPerServing / targetToGrams;

    // Factor: how many original servings = 1 of target unit
    return 1 / targetPerServing;
  }

  async function loadFoods() {
    loading = true;
    externalResults = [];
    try {
      foods = await api.searchFoods(
        searchQuery || undefined,
        selectedCategory || undefined,
        userOnly,
        200
      );

      // If searching and few local results, search external
      if (searchQuery.trim().length >= 2 && foods.length < 5 && !selectedCategory) {
        searchingExternal = true;
        try {
          externalResults = await api.searchExternalFoods(searchQuery);
          const localNames = new Set(foods.map(f => f.name.toLowerCase()));
          externalResults = externalResults.filter(r => !localNames.has(r.name.toLowerCase()));
        } catch (err) {
          console.error('External search failed:', err);
        } finally {
          searchingExternal = false;
        }
      }
    } catch (err) {
      console.error('Failed to load foods:', err);
    } finally {
      loading = false;
    }
  }

  async function importExternal(ext: ExternalFoodResult) {
    importingId = ext.external_id;
    try {
      await api.importExternalFood(ext);
      externalResults = externalResults.filter(r => r.external_id !== ext.external_id);
      loadFoods();
    } catch (err) {
      console.error('Import failed:', err);
    } finally {
      importingId = null;
    }
  }

  function sourceLabel(source: string): string {
    if (source === 'usda') return 'USDA';
    if (source === 'openfoodfacts') return 'Open Food Facts';
    return source;
  }

  onMount(loadFoods);

  let debounceTimer: ReturnType<typeof setTimeout>;
  function handleSearch() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadFoods, 300);
  }

  function handleNew() {
    editingFood = null;
    showForm = true;
  }

  function handleEdit(food: FoodItem) {
    editingFood = food;
    showForm = true;
  }

  async function handleDelete(food: FoodItem) {
    deleteError = '';
    try {
      await api.deleteFoodItem(food.id);
      loadFoods();
    } catch (err: any) {
      deleteError = err.message || 'Failed to delete';
    }
  }

  function togglePreview(food: FoodItem) {
    if (expandedFoodId === food.id) {
      expandedFoodId = null;
    } else {
      expandedFoodId = food.id;
      previewQty = 1;
      previewUnit = food.serving_unit;
    }
  }

  function handleSaved() {
    loadFoods();
  }
</script>

<svelte:head>
  <title>Food Database - Askesis</title>
</svelte:head>

<div>
  <!-- Header -->
  <div class="mb-6">
    <div class="flex items-center gap-2 mb-2">
      <a href="/nutrition" class="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
        <ChevronLeft size={20} />
      </a>
      <div>
        <h1 class="text-2xl font-bold">Food Database</h1>
        <p class="text-gray-500 text-sm mt-1">Manage your custom food items</p>
      </div>
    </div>
  </div>

  <!-- Search and filters -->
  <div class="card p-4 mb-4 space-y-3">
    <div class="relative">
      <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
      <input
        type="text"
        bind:value={searchQuery}
        on:input={handleSearch}
        placeholder="Search foods..."
        class="input pl-9"
      />
    </div>
    <div class="flex gap-3 items-center flex-wrap">
      <select bind:value={selectedCategory} on:change={loadFoods} class="input w-auto">
        <option value="">All categories</option>
        {#each CATEGORIES.filter(c => c) as cat}
          <option value={cat}>{cat}</option>
        {/each}
      </select>
      <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
        <input type="checkbox" bind:checked={userOnly} on:change={loadFoods} class="rounded" />
        My items only
      </label>
      <div class="flex-1"></div>
      <button on:click={handleNew} class="btn-primary flex items-center gap-2">
        <Plus size={16} />
        Add Food
      </button>
    </div>
  </div>

  {#if deleteError}
    <div class="text-sm text-red-500 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg mb-4">{deleteError}</div>
  {/if}

  <!-- Food list -->
  {#if loading}
    <p class="text-gray-500 text-center py-8">Loading...</p>
  {:else if foods.length === 0}
    <div class="text-center py-12 text-gray-500">
      <p class="text-lg mb-2">No food items found</p>
      <p class="text-sm">Add your first food to start building your database</p>
    </div>
  {:else}
    <div class="space-y-2">
      {#each foods as food}
        <div class="card overflow-hidden">
          <button
            type="button"
            on:click={() => togglePreview(food)}
            class="w-full p-4 flex items-center gap-4 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium">{food.name}</span>
                {#if food.brand}
                  <span class="text-sm text-gray-400">({food.brand})</span>
                {/if}
                {#if food.category}
                  <span class="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded-full text-gray-500">{food.category}</span>
                {/if}
                {#if food.is_shared}
                  <span class="text-xs px-2 py-0.5 bg-primary-50 dark:bg-primary-900/20 rounded-full text-primary-600 dark:text-primary-400">shared</span>
                {/if}
              </div>
              <div class="text-sm text-gray-500 mt-1 flex gap-3">
                <span>{food.serving_size}{food.serving_unit}</span>
                {#if food.calories}<span>{food.calories} cal</span>{/if}
                {#if food.protein_g}<span>P: {food.protein_g}g</span>{/if}
                {#if food.carbs_g}<span>C: {food.carbs_g}g</span>{/if}
                {#if food.fat_g}<span>F: {food.fat_g}g</span>{/if}
              </div>
            </div>
            <div class="flex items-center gap-1">
              {#if food.user_id}
                <span
                  role="button"
                  tabindex="0"
                  on:click|stopPropagation={() => handleEdit(food)}
                  on:keydown|stopPropagation={(e) => { if (e.key === 'Enter') handleEdit(food); }}
                  class="p-2 hover:bg-gray-200 dark:hover:bg-gray-600 rounded"
                  title="Edit"
                >
                  <Pencil size={16} />
                </span>
                <span
                  role="button"
                  tabindex="0"
                  on:click|stopPropagation={() => handleDelete(food)}
                  on:keydown|stopPropagation={(e) => { if (e.key === 'Enter') handleDelete(food); }}
                  class="p-2 hover:bg-gray-200 dark:hover:bg-gray-600 rounded text-red-500"
                  title="Delete"
                >
                  <Trash2 size={16} />
                </span>
              {/if}
              {#if expandedFoodId === food.id}
                <ChevronUp size={16} class="text-gray-400" />
              {:else}
                <ChevronDown size={16} class="text-gray-400" />
              {/if}
            </div>
          </button>

          {#if expandedFoodId === food.id}
            {@const factor = getConversionFactor(food, previewUnit) * previewQty}
            <div class="px-4 pb-4 border-t border-gray-100 dark:border-gray-700 pt-3">
              <!-- Unit selector -->
              <div class="flex items-center gap-2 mb-3 flex-wrap">
                <span class="text-sm text-gray-500">Unit:</span>
                {#each getAvailableUnits(food.serving_unit) as unit}
                  <button
                    on:click={() => { previewUnit = unit; previewQty = 1; }}
                    class="px-2.5 py-1 text-xs rounded-full transition-colors {previewUnit === unit ? 'bg-primary-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}"
                  >
                    {unit}
                  </button>
                {/each}
              </div>

              <!-- Quantity slider -->
              <div class="flex items-center gap-3 mb-3">
                <span class="text-sm text-gray-500 w-12">Qty:</span>
                <button
                  on:click={() => { if (previewQty > 0.5) previewQty = Math.round((previewQty - 0.5) * 10) / 10; }}
                  class="p-1 rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
                  disabled={previewQty <= 0.5}
                >
                  <Minus size={14} />
                </button>
                <input
                  type="range"
                  min="0.5"
                  max="10"
                  step="0.5"
                  bind:value={previewQty}
                  class="flex-1 accent-primary-500"
                />
                <button
                  on:click={() => { if (previewQty < 10) previewQty = Math.round((previewQty + 0.5) * 10) / 10; }}
                  class="p-1 rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
                  disabled={previewQty >= 10}
                >
                  <Plus size={14} />
                </button>
                <span class="text-sm font-medium w-24 text-right">
                  {previewQty} {previewUnit}
                </span>
              </div>

              <!-- Scaled nutrition -->
              <div class="grid grid-cols-2 sm:grid-cols-5 gap-2">
                <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                  <div class="text-lg font-bold text-nutrition-500">{food.calories ? Math.round(food.calories * factor) : '—'}</div>
                  <div class="text-xs text-gray-500">Calories</div>
                </div>
                <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                  <div class="text-lg font-bold text-red-500">{food.protein_g ? Math.round(food.protein_g * factor * 10) / 10 : '—'}</div>
                  <div class="text-xs text-gray-500">Protein (g)</div>
                </div>
                <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                  <div class="text-lg font-bold text-amber-500">{food.carbs_g ? Math.round(food.carbs_g * factor * 10) / 10 : '—'}</div>
                  <div class="text-xs text-gray-500">Carbs (g)</div>
                </div>
                <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                  <div class="text-lg font-bold text-blue-500">{food.fat_g ? Math.round(food.fat_g * factor * 10) / 10 : '—'}</div>
                  <div class="text-xs text-gray-500">Fat (g)</div>
                </div>
                {#if food.fiber_g}
                  <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center">
                    <div class="text-lg font-bold text-green-500">{Math.round(food.fiber_g * factor * 10) / 10}</div>
                    <div class="text-xs text-gray-500">Fiber (g)</div>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
    <p class="text-xs text-gray-400 text-center mt-4">{foods.length} item{foods.length !== 1 ? 's' : ''}</p>
  {/if}

  <!-- External results -->
  {#if searchingExternal}
    <div class="flex items-center justify-center gap-2 py-4 text-sm text-gray-400">
      <div class="w-4 h-4 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin"></div>
      Searching USDA & Open Food Facts...
    </div>
  {/if}

  {#if externalResults.length > 0}
    <div class="mt-6">
      <div class="flex items-center gap-2 mb-3">
        <Globe size={16} class="text-blue-500" />
        <h2 class="text-sm font-medium text-gray-600 dark:text-gray-400">External Results</h2>
        <span class="text-xs text-gray-400">Click to add to your database</span>
      </div>
      <div class="space-y-2">
        {#each externalResults as ext}
          <button
            type="button"
            on:click={() => importExternal(ext)}
            disabled={importingId === ext.external_id}
            class="card p-4 w-full text-left flex items-center gap-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors disabled:opacity-50"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium">{ext.name}</span>
                {#if ext.brand}
                  <span class="text-sm text-gray-400">({ext.brand})</span>
                {/if}
              </div>
              <div class="text-sm text-gray-500 mt-1 flex gap-3">
                <span>{ext.serving_size}{ext.serving_unit}</span>
                {#if ext.calories}<span>{ext.calories} cal</span>{/if}
                {#if ext.protein_g}<span>P: {ext.protein_g}g</span>{/if}
                {#if ext.carbs_g}<span>C: {ext.carbs_g}g</span>{/if}
                {#if ext.fat_g}<span>F: {ext.fat_g}g</span>{/if}
              </div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 rounded-full text-blue-500">{sourceLabel(ext.source)}</span>
              {#if importingId === ext.external_id}
                <div class="w-4 h-4 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin"></div>
              {:else}
                <Download size={16} class="text-gray-400" />
              {/if}
            </div>
          </button>
        {/each}
      </div>
    </div>
  {/if}
</div>

<FoodItemForm
  bind:show={showForm}
  editItem={editingFood}
  on:saved={handleSaved}
/>
