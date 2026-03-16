<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { Search, Plus, X, Minus, Globe, Download } from 'lucide-svelte';
  import { api, type FoodItem, type MealFoodItemInput, type ExternalFoodResult } from '$lib/api/client';

  export let selectedFoods: { food: FoodItem; quantity: number; notes?: string }[] = [];

  const dispatch = createEventDispatcher<{
    change: MealFoodItemInput[];
    createNew: string;
  }>();

  let query = '';
  let results: FoodItem[] = [];
  let externalResults: ExternalFoodResult[] = [];
  let searching = false;
  let searchingExternal = false;
  let showDropdown = false;
  let debounceTimer: ReturnType<typeof setTimeout>;
  let importingId: string | null = null;

  function handleInput() {
    clearTimeout(debounceTimer);
    externalResults = [];
    if (!query.trim()) {
      results = [];
      showDropdown = false;
      return;
    }
    debounceTimer = setTimeout(async () => {
      searching = true;
      try {
        results = await api.searchFoods(query);
        showDropdown = true;

        // If local results are sparse, search external DBs
        if (results.length < 5 && query.trim().length >= 2) {
          searchingExternal = true;
          try {
            externalResults = await api.searchExternalFoods(query);
            // Filter out items that match local results by name
            const localNames = new Set(results.map(r => r.name.toLowerCase()));
            externalResults = externalResults.filter(r => !localNames.has(r.name.toLowerCase()));
          } catch (err) {
            console.error('External search failed:', err);
          } finally {
            searchingExternal = false;
          }
        }
      } catch (err) {
        console.error('Search failed:', err);
      } finally {
        searching = false;
      }
    }, 300);
  }

  function addFood(food: FoodItem) {
    // Don't add duplicates
    if (selectedFoods.some(sf => sf.food.id === food.id)) return;
    selectedFoods = [...selectedFoods, { food, quantity: 1 }];
    query = '';
    showDropdown = false;
    results = [];
    externalResults = [];
    emitChange();
  }

  async function importAndAdd(ext: ExternalFoodResult) {
    importingId = ext.external_id;
    try {
      const food = await api.importExternalFood(ext);
      addFood(food);
    } catch (err) {
      console.error('Import failed:', err);
    } finally {
      importingId = null;
    }
  }

  function removeFood(index: number) {
    selectedFoods = selectedFoods.filter((_, i) => i !== index);
    emitChange();
  }

  function updateQuantity(index: number, delta: number) {
    const item = selectedFoods[index];
    const newQty = Math.max(0.5, Math.round((item.quantity + delta) * 2) / 2);
    selectedFoods[index] = { ...item, quantity: newQty };
    selectedFoods = [...selectedFoods];
    emitChange();
  }

  function setQuantity(index: number, value: number) {
    if (value > 0) {
      selectedFoods[index] = { ...selectedFoods[index], quantity: value };
      selectedFoods = [...selectedFoods];
      emitChange();
    }
  }

  function emitChange() {
    dispatch('change', selectedFoods.map(sf => ({
      food_item_id: sf.food.id,
      quantity: sf.quantity,
      notes: sf.notes,
    })));
  }

  function handleCreateNew() {
    dispatch('createNew', query);
    query = '';
    showDropdown = false;
  }

  function handleBlur() {
    // Delay to allow click on dropdown items
    setTimeout(() => { showDropdown = false; }, 200);
  }

  function sourceLabel(source: string): string {
    if (source === 'usda') return 'USDA';
    if (source === 'openfoodfacts') return 'Open Food Facts';
    return source;
  }

  $: totals = selectedFoods.reduce(
    (acc, { food, quantity }) => ({
      calories: acc.calories + (food.calories ? Math.round(food.calories * quantity) : 0),
      protein_g: acc.protein_g + (food.protein_g ? Math.round(food.protein_g * quantity * 10) / 10 : 0),
      carbs_g: acc.carbs_g + (food.carbs_g ? Math.round(food.carbs_g * quantity * 10) / 10 : 0),
      fat_g: acc.fat_g + (food.fat_g ? Math.round(food.fat_g * quantity * 10) / 10 : 0),
    }),
    { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 }
  );
</script>

<div class="space-y-3">
  <!-- Search input -->
  <div class="relative">
    <div class="relative">
      <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
      <input
        type="text"
        bind:value={query}
        on:input={handleInput}
        on:focus={() => { if (results.length || externalResults.length) showDropdown = true; }}
        on:blur={handleBlur}
        placeholder="Search foods..."
        class="input pl-9"
      />
      {#if searching}
        <div class="absolute right-3 top-1/2 -translate-y-1/2">
          <div class="w-4 h-4 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin"></div>
        </div>
      {/if}
    </div>

    <!-- Dropdown results -->
    {#if showDropdown}
      <div class="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-80 overflow-y-auto">
        {#if results.length === 0 && externalResults.length === 0 && !searchingExternal && query.trim()}
          <div class="p-3 text-sm text-gray-500">
            No foods found for "{query}"
          </div>
        {/if}

        <!-- Local results -->
        {#each results as food}
          <button
            type="button"
            class="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center justify-between border-b border-gray-100 dark:border-gray-700 last:border-0"
            on:mousedown|preventDefault={() => addFood(food)}
          >
            <div>
              <span class="font-medium text-sm">{food.name}</span>
              {#if food.brand}
                <span class="text-xs text-gray-400 ml-1">({food.brand})</span>
              {/if}
              <div class="text-xs text-gray-500">
                {food.serving_size}{food.serving_unit}
                {#if food.calories} · {food.calories} cal{/if}
              </div>
            </div>
            {#if food.category}
              <span class="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded-full text-gray-500">{food.category}</span>
            {/if}
          </button>
        {/each}

        <!-- External results -->
        {#if externalResults.length > 0}
          <div class="px-3 py-1.5 bg-gray-50 dark:bg-gray-900 border-t border-b border-gray-200 dark:border-gray-700 flex items-center gap-1.5">
            <Globe size={12} class="text-gray-400" />
            <span class="text-xs text-gray-500 font-medium">External databases</span>
          </div>
          {#each externalResults as ext}
            <button
              type="button"
              class="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center justify-between border-b border-gray-100 dark:border-gray-700 last:border-0"
              on:mousedown|preventDefault={() => importAndAdd(ext)}
              disabled={importingId === ext.external_id}
            >
              <div>
                <span class="font-medium text-sm">{ext.name}</span>
                {#if ext.brand}
                  <span class="text-xs text-gray-400 ml-1">({ext.brand})</span>
                {/if}
                <div class="text-xs text-gray-500">
                  {ext.serving_size}{ext.serving_unit}
                  {#if ext.calories} · {ext.calories} cal{/if}
                </div>
              </div>
              <div class="flex items-center gap-1.5">
                <span class="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 rounded-full text-blue-500">{sourceLabel(ext.source)}</span>
                {#if importingId === ext.external_id}
                  <div class="w-3 h-3 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin"></div>
                {:else}
                  <Download size={12} class="text-gray-400" />
                {/if}
              </div>
            </button>
          {/each}
        {/if}

        {#if searchingExternal}
          <div class="px-3 py-2 flex items-center gap-2 text-xs text-gray-400">
            <div class="w-3 h-3 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin"></div>
            Searching external databases...
          </div>
        {/if}

        {#if query.trim()}
          <button
            type="button"
            class="w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2 text-primary-500 text-sm font-medium border-t border-gray-100 dark:border-gray-700"
            on:mousedown|preventDefault={handleCreateNew}
          >
            <Plus size={14} />
            Create "{query}" as new food
          </button>
        {/if}
      </div>
    {/if}
  </div>

  <!-- Selected foods list -->
  {#if selectedFoods.length > 0}
    <div class="space-y-2">
      {#each selectedFoods as { food, quantity }, i}
        <div class="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium truncate">{food.name}</div>
            <div class="text-xs text-gray-500">
              {food.serving_size}{food.serving_unit}
              {#if food.calories} · {Math.round(food.calories * quantity)} cal{/if}
            </div>
          </div>
          <div class="flex items-center gap-1">
            <button
              type="button"
              on:click={() => updateQuantity(i, -0.5)}
              class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700"
            >
              <Minus size={14} />
            </button>
            <input
              type="number"
              value={quantity}
              on:change={(e) => setQuantity(i, parseFloat(e.currentTarget.value))}
              class="w-14 text-center text-sm input py-1 px-1"
              step="0.5"
              min="0.5"
            />
            <button
              type="button"
              on:click={() => updateQuantity(i, 0.5)}
              class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700"
            >
              <Plus size={14} />
            </button>
          </div>
          <button
            type="button"
            on:click={() => removeFood(i)}
            class="p-1 text-gray-400 hover:text-red-500"
          >
            <X size={14} />
          </button>
        </div>
      {/each}

      <!-- Totals -->
      <div class="flex gap-4 text-xs text-gray-500 px-2 pt-1 border-t border-gray-200 dark:border-gray-700">
        <span><strong>{totals.calories}</strong> cal</span>
        <span>P: {totals.protein_g}g</span>
        <span>C: {totals.carbs_g}g</span>
        <span>F: {totals.fat_g}g</span>
      </div>
    </div>
  {/if}
</div>
