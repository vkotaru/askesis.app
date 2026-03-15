<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { X } from 'lucide-svelte';
  import { api, type FoodItem, type FoodItemInput } from '$lib/api/client';

  export let show = false;
  export let editItem: FoodItem | null = null;
  export let initialName = '';

  const dispatch = createEventDispatcher<{
    saved: FoodItem;
    close: void;
  }>();

  const CATEGORIES = [
    'Fruit', 'Vegetable', 'Grain', 'Dairy', 'Meat', 'Seafood',
    'Legume', 'Nut', 'Beverage', 'Snack', 'Condiment', 'Other'
  ];

  const SERVING_UNITS = ['g', 'ml', 'oz', 'cup', 'piece', 'tbsp', 'tsp', 'slice'];

  let name = '';
  let brand = '';
  let category = '';
  let serving_size = 1;
  let serving_unit = 'g';
  let calories: number | undefined;
  let protein_g: number | undefined;
  let carbs_g: number | undefined;
  let fat_g: number | undefined;
  let fiber_g: number | undefined;
  let is_shared = true;
  let saving = false;
  let error = '';

  $: if (show) {
    if (editItem) {
      name = editItem.name;
      brand = editItem.brand || '';
      category = editItem.category || '';
      serving_size = editItem.serving_size;
      serving_unit = editItem.serving_unit;
      calories = editItem.calories;
      protein_g = editItem.protein_g;
      carbs_g = editItem.carbs_g;
      fat_g = editItem.fat_g;
      fiber_g = editItem.fiber_g;
      is_shared = editItem.is_shared;
    } else {
      name = initialName;
      brand = '';
      category = '';
      serving_size = 1;
      serving_unit = 'g';
      calories = undefined;
      protein_g = undefined;
      carbs_g = undefined;
      fat_g = undefined;
      fiber_g = undefined;
      is_shared = true;
    }
    error = '';
  }

  async function handleSubmit() {
    if (!name.trim()) {
      error = 'Name is required';
      return;
    }

    saving = true;
    error = '';

    const data: FoodItemInput = {
      name: name.trim(),
      brand: brand.trim() || undefined,
      category: category || undefined,
      serving_size,
      serving_unit,
      calories,
      protein_g,
      carbs_g,
      fat_g,
      fiber_g,
      is_shared,
    };

    try {
      let saved: FoodItem;
      if (editItem) {
        saved = await api.updateFoodItem(editItem.id, data);
      } else {
        saved = await api.createFoodItem(data);
      }
      dispatch('saved', saved);
      show = false;
    } catch (err: any) {
      error = err.message || 'Failed to save';
    } finally {
      saving = false;
    }
  }

  function close() {
    show = false;
    dispatch('close');
  }
</script>

{#if show}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" on:click|self={close}>
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
      <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <h2 class="text-lg font-semibold">{editItem ? 'Edit Food' : 'New Food Item'}</h2>
        <button type="button" on:click={close} class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
          <X size={20} />
        </button>
      </div>

      <form on:submit|preventDefault={handleSubmit} class="p-4 space-y-4">
        {#if error}
          <div class="text-sm text-red-500 bg-red-50 dark:bg-red-900/20 p-2 rounded">{error}</div>
        {/if}

        <div>
          <label class="label">Name *</label>
          <input type="text" bind:value={name} class="input" placeholder="e.g. Greek Yogurt" required />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="label">Brand</label>
            <input type="text" bind:value={brand} class="input" placeholder="Optional" />
          </div>
          <div>
            <label class="label">Category</label>
            <select bind:value={category} class="input">
              <option value="">Select...</option>
              {#each CATEGORIES as cat}
                <option value={cat}>{cat}</option>
              {/each}
            </select>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="label">Serving Size</label>
            <input type="number" bind:value={serving_size} class="input" min="0.1" step="0.1" />
          </div>
          <div>
            <label class="label">Unit</label>
            <select bind:value={serving_unit} class="input">
              {#each SERVING_UNITS as unit}
                <option value={unit}>{unit}</option>
              {/each}
            </select>
          </div>
        </div>

        <div class="border-t border-gray-200 dark:border-gray-700 pt-4">
          <p class="label mb-2">Nutrition (per serving)</p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-xs text-gray-500">Calories</label>
              <input type="number" bind:value={calories} class="input" min="0" />
            </div>
            <div>
              <label class="text-xs text-gray-500">Protein (g)</label>
              <input type="number" bind:value={protein_g} class="input" min="0" step="0.1" />
            </div>
            <div>
              <label class="text-xs text-gray-500">Carbs (g)</label>
              <input type="number" bind:value={carbs_g} class="input" min="0" step="0.1" />
            </div>
            <div>
              <label class="text-xs text-gray-500">Fat (g)</label>
              <input type="number" bind:value={fat_g} class="input" min="0" step="0.1" />
            </div>
            <div>
              <label class="text-xs text-gray-500">Fiber (g)</label>
              <input type="number" bind:value={fiber_g} class="input" min="0" step="0.1" />
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <input type="checkbox" id="is_shared" bind:checked={is_shared} class="rounded" />
          <label for="is_shared" class="text-sm text-gray-600 dark:text-gray-400">
            Share with family & friends
          </label>
        </div>

        <div class="flex justify-end gap-3 pt-2">
          <button type="button" on:click={close} class="btn-secondary">Cancel</button>
          <button type="submit" class="btn-primary" disabled={saving}>
            {saving ? 'Saving...' : (editItem ? 'Update' : 'Create')}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
