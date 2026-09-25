<script lang="ts">
  /**
   * Saved workouts you repeat.
   *
   * A routine is a plan: movements in an order, with the sets and reps you
   * intend. It is deliberately not a log — starting a session from one copies
   * the movements across and leaves every number blank, so "what I planned" and
   * "what I did" stay separable. If the targets were prefilled as results, the
   * question a routine exists to answer would stop working.
   *
   * Unlike the exercise catalogue, routines are per-account: the movements are
   * shared with the household, the programming is yours.
   */
  import { onMount } from 'svelte';
  import { Plus, X, Trash2, Pencil, Search, ListChecks } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { offlineApi } from '$lib/stores/data';
  import {
    api,
    type Routine,
    type RoutineExercise,
    type CatalogEntry,
  } from '$lib/api/client';

  let routines: Routine[] = [];
  let catalog: CatalogEntry[] = [];
  let loading = true;
  let error = '';

  let showForm = false;
  let editingId: number | null = null;
  let formName = '';
  let formDuration: string = '';
  let formExercises: RoutineExercise[] = [];

  let showPicker = false;
  let pickerQuery = '';

  onMount(load);

  async function load() {
    loading = true;
    try {
      [routines, catalog] = await Promise.all([api.getRoutines(), offlineApi.getCatalog()]);
      error = '';
    } catch {
      error = 'Could not load routines.';
    } finally {
      loading = false;
    }
  }

  function openNew() {
    editingId = null;
    formName = '';
    formDuration = '';
    formExercises = [];
    showForm = true;
  }

  function openEdit(routine: Routine) {
    editingId = routine.id;
    formName = routine.name;
    formDuration = routine.default_duration_mins?.toString() ?? '';
    // Copy, so cancelling leaves the loaded list untouched.
    formExercises = routine.exercises.map((e) => ({ ...e }));
    showForm = true;
  }

  async function save() {
    if (!formName.trim()) return;
    const payload = {
      name: formName.trim(),
      default_duration_mins: formDuration ? parseInt(formDuration) : null,
      exercises: formExercises,
    };
    try {
      if (editingId) await api.updateRoutine(editingId, payload);
      else await api.createRoutine(payload);
      showForm = false;
      await load();
    } catch {
      error = 'Could not save the routine.';
    }
  }

  async function remove(routine: Routine) {
    try {
      await api.deleteRoutine(routine.id);
      await load();
    } catch {
      error = 'Could not delete the routine.';
    }
  }

  function addFromCatalog(entry: CatalogEntry) {
    formExercises = [...formExercises, { name: entry.name, catalog_id: entry.id }];
    showPicker = false;
    pickerQuery = '';
  }

  function removeExercise(index: number) {
    formExercises = formExercises.filter((_, i) => i !== index);
  }

  $: filteredCatalog = pickerQuery
    ? catalog.filter((c) => c.name.toLowerCase().includes(pickerQuery.toLowerCase()))
    : catalog;

  function summary(routine: Routine): string {
    if (routine.exercises.length === 0) return 'No exercises yet';
    return routine.exercises.map((e) => e.name).join(' · ');
  }
</script>

<svelte:head><title>Routines · Askesis</title></svelte:head>

<div>
  <div class="mb-6">
    <h1 class="text-2xl font-bold">Routines</h1>
    <p class="text-sm text-gray-500">Saved workouts you repeat</p>
  </div>

  {#if error}
    <p class="mb-4 text-sm text-red-500">{error}</p>
  {/if}

  {#if !showForm}
    <button
      type="button"
      on:click={openNew}
      class="w-full mb-4 py-2 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-500 hover:border-primary-400 hover:text-primary-600 flex items-center justify-center gap-1"
    >
      <Plus size={16} /> New routine
    </button>
  {/if}

  {#if showForm}
    <div class="card p-4 md:p-6 mb-6 space-y-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label for="routine-name" class="label">Name</label>
          <input
            id="routine-name"
            bind:value={formName}
            placeholder="Push A"
            class="input"
          />
        </div>
        <div>
          <label for="routine-duration" class="label">
            Usual length <span class="text-gray-400 font-normal">(min)</span>
          </label>
          <input
            id="routine-duration"
            type="number"
            inputmode="numeric"
            bind:value={formDuration}
            placeholder="60"
            class="input"
          />
        </div>
      </div>

      <div class="space-y-2">
        <span class="label">Exercises</span>
        {#each formExercises as exercise, i}
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-2 space-y-2">
            <div class="flex items-center gap-2">
              <span class="text-sm flex-1 truncate">{exercise.name}</span>
              <button
                type="button"
                class="p-1 text-gray-400 hover:text-red-500"
                on:click={() => removeExercise(i)}
              >
                <X size={14} />
              </button>
            </div>
            <!-- Targets, not results. Starting a session copies the movements
                 and leaves the numbers blank. -->
            <div class="grid grid-cols-3 gap-2">
              <div>
                <span class="text-[10px] text-gray-400">sets</span>
                <input
                  type="number"
                  inputmode="numeric"
                  bind:value={exercise.target_sets}
                  placeholder="—"
                  class="input py-1 text-sm tabular-nums"
                />
              </div>
              <div>
                <span class="text-[10px] text-gray-400">reps</span>
                <input
                  type="number"
                  inputmode="numeric"
                  bind:value={exercise.target_reps}
                  placeholder="—"
                  class="input py-1 text-sm tabular-nums"
                />
              </div>
              <div>
                <span class="text-[10px] text-gray-400">kg</span>
                <input
                  type="number"
                  step="any"
                  inputmode="decimal"
                  bind:value={exercise.target_weight_kg}
                  placeholder="—"
                  class="input py-1 text-sm tabular-nums"
                />
              </div>
            </div>
          </div>
        {/each}

        <button
          type="button"
          on:click={() => (showPicker = true)}
          class="w-full py-1.5 text-xs text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded"
        >
          + Add exercise
        </button>
      </div>

      <div class="flex justify-end gap-2">
        <button type="button" class="btn-secondary" on:click={() => (showForm = false)}>
          Cancel
        </button>
        <button type="button" class="btn-primary" on:click={save}>
          {editingId ? 'Update routine' : 'Save routine'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else if routines.length === 0 && !showForm}
    <div class="card p-8 text-center">
      <ListChecks size={32} class="mx-auto text-gray-300 mb-3" />
      <p class="text-gray-500">No routines yet</p>
      <p class="text-sm text-gray-400">
        Save a workout here and you can start a session from it
      </p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each routines as routine}
        <div class="card p-4 flex items-start gap-3">
          <div class="flex-1 min-w-0">
            <p class="font-medium">{routine.name}</p>
            <p class="text-xs text-gray-400 truncate">{summary(routine)}</p>
            {#if routine.default_duration_mins}
              <p class="text-[10px] text-gray-400">~{routine.default_duration_mins} min</p>
            {/if}
          </div>
          <button
            type="button"
            title="Edit"
            class="p-1 text-gray-400 hover:text-primary-500"
            on:click={() => openEdit(routine)}
          >
            <Pencil size={16} />
          </button>
          <button
            type="button"
            title="Delete"
            class="p-1 text-gray-400 hover:text-red-500"
            on:click={() => remove(routine)}
          >
            <Trash2 size={16} />
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if showPicker}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="fixed inset-0 z-[70] bg-black/50 flex items-end sm:items-center justify-center"
    on:click={() => (showPicker = false)}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="bg-white dark:bg-gray-800 w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-4 space-y-3 max-h-[80vh] flex flex-col"
      on:click|stopPropagation
    >
      <div class="flex items-center gap-2">
        <Search size={16} class="text-gray-400" />
        <input bind:value={pickerQuery} placeholder="Search exercises" class="input flex-1" />
        <button type="button" class="p-1 text-gray-400" on:click={() => (showPicker = false)}>
          <X size={18} />
        </button>
      </div>
      <div class="flex-1 overflow-y-auto space-y-1">
        {#each filteredCatalog as entry}
          <button
            type="button"
            class="w-full text-left px-3 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-sm"
            on:click={() => addFromCatalog(entry)}
          >
            {entry.name}
          </button>
        {:else}
          <p class="text-xs text-gray-400 px-3 py-2">
            Nothing matches. Exercises are added from the workout logger.
          </p>
        {/each}
      </div>
    </div>
  </div>
{/if}
