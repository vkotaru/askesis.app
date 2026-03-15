<script lang="ts">
  import { onMount } from 'svelte';
  import { Search, Plus, Pencil, Trash2, ChevronLeft } from 'lucide-svelte';
  import FoodItemForm from '$lib/components/FoodItemForm.svelte';
  import { api, type FoodItem } from '$lib/api/client';

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

  async function loadFoods() {
    loading = true;
    try {
      foods = await api.searchFoods(
        searchQuery || undefined,
        selectedCategory || undefined,
        userOnly,
        200
      );
    } catch (err) {
      console.error('Failed to load foods:', err);
    } finally {
      loading = false;
    }
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
        <div class="card p-4 flex items-center gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
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
          {#if food.user_id}
            <div class="flex gap-1">
              <button
                on:click={() => handleEdit(food)}
                class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                title="Edit"
              >
                <Pencil size={16} />
              </button>
              <button
                on:click={() => handleDelete(food)}
                class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded text-red-500"
                title="Delete"
              >
                <Trash2 size={16} />
              </button>
            </div>
          {/if}
        </div>
      {/each}
    </div>
    <p class="text-xs text-gray-400 text-center mt-4">{foods.length} item{foods.length !== 1 ? 's' : ''}</p>
  {/if}
</div>

<FoodItemForm
  bind:show={showForm}
  editItem={editingFood}
  on:saved={handleSaved}
/>
