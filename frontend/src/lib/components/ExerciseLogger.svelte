<script lang="ts">
  /**
   * Logs the contents of a strength session: exercises, and the sets inside them.
   *
   * Follows `FoodSearch.svelte`'s shape — this component owns the array, mutates
   * it by reassignment so Svelte notices, and the parent binds to it. It does no
   * saving of its own; the activity form owns the request.
   *
   * Two things drive the design, both from what logging actually feels like
   * standing in a gym:
   *
   * - **Last session is shown, not remembered.** Each input carries what you did
   *   for that movement last time as its placeholder, so the job is confirming or
   *   beating a number rather than recalling one. That is the single thing that
   *   makes this faster than a notes app.
   * - **Adding a set copies the one above it.** Sets in a working block are
   *   usually the same weight, so the default should be "again" and the edit
   *   should be the exception.
   */
  import { Plus, X, Search, ExternalLink, StickyNote, Trash2 } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { offlineApi } from '$lib/stores/data';
  import { settings } from '$lib/stores/settings';
  import { weightFromMetric, weightToMetric, getWeightLabel } from '$lib/utils/units';
  import {
    ApiError,
    api,
    type Exercise,
    type ExerciseSet,
    type CatalogEntry,
    type LastSession,
    type SetType,
    type Routine,
  } from '$lib/api/client';

  export let exercises: Exercise[] = [];

  /**
   * Weights are held in kilograms and shown in the user's unit.
   *
   * Everything in this app persists canonical metric and converts at the edge;
   * this component is an edge. Logging in pounds and storing the number
   * unconverted would silently rewrite a person's whole training history by a
   * factor of 2.2 — and it would look right on the screen that entered it.
   */
  $: unit = $settings.weight_unit;
  $: weightLabel = getWeightLabel(unit);

  function toDisplay(kg: number | null | undefined): string {
    if (kg == null) return '';
    return String(Math.round(weightFromMetric(kg, unit) * 100) / 100);
  }

  function fromDisplay(raw: string): number | null {
    const value = parseFloat(raw);
    if (!isFinite(value)) return null;
    return Math.round(weightToMetric(value, unit) * 1000) / 1000;
  }

  let catalog: CatalogEntry[] = [];
  let catalogError = '';
  let showPicker = false;
  let pickerQuery = '';
  let creating = false;

  /** Last-session sets per catalogue id. Fetched once per exercise, then reused. */
  let lastByCatalogId: Record<number, LastSession> = {};

  /** Saved workouts, offered only while the session is still empty. */
  let routines: Routine[] = [];
  void (async () => {
    try {
      routines = await api.getRoutines();
    } catch {
      // Offline or none saved — the shortcut simply does not appear.
    }
  })();
  /** Which exercise cards have their note field open.
   *
   * An array rather than a map keyed by index: the two must stay aligned when a
   * card is removed, and a plain map silently hands the deleted card's open
   * state to whichever exercise slid into its slot.
   */
  let noteOpen: boolean[] = [];

  const SET_TYPES: SetType[] = ['warmup', 'working', 'failure'];
  const TYPE_LABEL: Record<SetType, string> = { warmup: 'W', working: '·', failure: 'F' };
  const TYPE_TITLE: Record<SetType, string> = {
    warmup: 'Warm-up — not counted in volume',
    working: 'Working set',
    failure: 'Taken to failure',
  };

  async function loadCatalog() {
    try {
      catalog = await offlineApi.getCatalog(pickerQuery || undefined);
      catalogError = '';
    } catch {
      catalogError = 'Could not load the exercise list.';
    }
  }

  function openPicker() {
    showPicker = true;
    pickerQuery = '';
    loadCatalog();
  }

  async function addExercise(entry: CatalogEntry) {
    exercises = [
      ...exercises,
      {
        name: entry.name,
        catalog_id: entry.id,
        position: exercises.length,
        sets_detail: [{ set_number: 1, weight_kg: null, reps: null, set_type: 'working' }],
      },
    ];
    showPicker = false;
    emit();
    void loadLast(entry.id);
  }

  /** Create a movement that is not in the library yet, without leaving the session. */
  async function createAndAdd() {
    const name = pickerQuery.trim();
    if (!name || creating) return;
    creating = true;
    try {
      const entry = await offlineApi.createCatalogEntry({ name });
      catalog = [...catalog, entry];
      await addExercise(entry);
    } catch (err) {
      // 409 means someone already added it — the other account, or you on
      // another device. Link to the existing entry rather than treating this
      // like being offline, which would log an unlinked duplicate and lose the
      // video and the last-time numbers for no reason.
      if (err instanceof ApiError && err.status === 409) {
        try {
          const matches = await offlineApi.getCatalog(name);
          const found = matches.find(
            (c) => c.name.toLowerCase() === name.toLowerCase()
          );
          if (found) {
            catalog = [...catalog.filter((c) => c.id !== found.id), found];
            await addExercise(found);
            creating = false;
            return;
          }
        } catch {
          // Fall through to the unlinked fallback below.
        }
      }
      // Offline, most likely. Fall back to a plain named exercise so the set is
      // still logged — it just has no catalogue link, so no video and no
      // last-time numbers until it is added to the library properly.
      exercises = [
        ...exercises,
        {
          name,
          position: exercises.length,
          sets_detail: [
            { set_number: 1, weight_kg: null, reps: null, set_type: 'working' },
          ],
        },
      ];
      showPicker = false;
      emit();
      catalogError = '';
    } finally {
      creating = false;
    }
  }

  /** Ids already fetched, *including the ones that failed*. */
  const lastAttempted = new Set<number>();

  async function loadLast(catalogId: number) {
    // The reactive prefetch below re-runs on every keystroke in the logger.
    // Keying off `lastByCatalogId` alone only suppresses a repeat after a
    // success, so an offline session fired one request per character typed.
    if (lastAttempted.has(catalogId)) return;
    lastAttempted.add(catalogId);
    try {
      const last = await api.getLastSession(catalogId);
      lastByCatalogId = { ...lastByCatalogId, [catalogId]: last };
    } catch {
      // Offline, or no history — the placeholders simply stay blank.
    }
  }

  function removeExercise(index: number) {
    exercises = exercises.filter((_, i) => i !== index).map((e, i) => ({ ...e, position: i }));
    noteOpen = noteOpen.filter((_, i) => i !== index);
    emit();
  }

  function addSet(index: number) {
    const sets = exercises[index].sets_detail ?? [];
    const previous = sets[sets.length - 1];
    const next: ExerciseSet = {
      set_number: sets.length + 1,
      // Repeat the last set rather than starting empty: within a block the
      // weight usually holds, so "same again" is the common case.
      weight_kg: previous?.weight_kg ?? null,
      reps: previous?.reps ?? null,
      set_type: previous?.set_type ?? 'working',
    };
    exercises[index] = { ...exercises[index], sets_detail: [...sets, next] };
    exercises = exercises;
    emit();
  }

  /** Write a typed weight back as kilograms. */
  function setWeight(exerciseIndex: number, setIndex: number, raw: string) {
    const sets = [...(exercises[exerciseIndex].sets_detail ?? [])];
    sets[setIndex] = { ...sets[setIndex], weight_kg: fromDisplay(raw) };
    exercises[exerciseIndex] = { ...exercises[exerciseIndex], sets_detail: sets };
    emit();
  }

  function removeSet(exerciseIndex: number, setIndex: number) {
    const sets = (exercises[exerciseIndex].sets_detail ?? [])
      .filter((_, i) => i !== setIndex)
      .map((s, i) => ({ ...s, set_number: i + 1 }));
    exercises[exerciseIndex] = { ...exercises[exerciseIndex], sets_detail: sets };
    exercises = exercises;
    emit();
  }

  function cycleType(exerciseIndex: number, setIndex: number) {
    const sets = [...(exercises[exerciseIndex].sets_detail ?? [])];
    const current = sets[setIndex].set_type;
    const next = SET_TYPES[(SET_TYPES.indexOf(current) + 1) % SET_TYPES.length];
    sets[setIndex] = { ...sets[setIndex], set_type: next };
    exercises[exerciseIndex] = { ...exercises[exerciseIndex], sets_detail: sets };
    exercises = exercises;
    emit();
  }

  /**
   * Start this session from a saved routine.
   *
   * Copies the movements and **not** the targets. A routine's `target_reps` is
   * what you meant to do; writing it into the set would record it as what you
   * did, and then "did I hit my targets" compares a number against itself. The
   * placeholders from last session still apply, which is the honest prefill.
   */
  function applyRoutine(routine: Routine) {
    exercises = routine.exercises.map((r, i) => ({
      name: r.name,
      catalog_id: r.catalog_id ?? null,
      position: i,
      sets_detail: Array.from({ length: r.target_sets ?? 1 }, (_, n) => ({
        set_number: n + 1,
        weight_kg: null,
        reps: null,
        set_type: 'working' as SetType,
      })),
    }));
    emit();
    for (const r of routine.exercises) if (r.catalog_id) void loadLast(r.catalog_id);
  }

  /** Tell Svelte the array changed.
   *
   * The parent uses `bind:exercises`, so it already shares these objects; what
   * it does not get from a nested mutation is reactivity. Reassigning is what
   * makes the volume line and the parent's own derived state recompute.
   */
  function emit() {
    exercises = exercises;
  }

  /**
   * Tapping an empty field accepts last session's number for it.
   *
   * The previous values are shown as placeholders rather than prefilled on
   * purpose — a set you never performed must not end up in the history just
   * because the app guessed. But making you retype six identical numbers to
   * repeat a workout is the thing that makes people stop logging, so one tap
   * accepts and any edit overrides.
   */
  function acceptLast(exerciseIndex: number, setIndex: number, field: 'weight_kg' | 'reps') {
    const sets = [...(exercises[exerciseIndex].sets_detail ?? [])];
    if (sets[setIndex]?.[field] != null) return; // already has a value — leave it
    const previous = lastSet(exercises[exerciseIndex], setIndex);
    const value = previous?.[field];
    if (value == null) return;
    sets[setIndex] = { ...sets[setIndex], [field]: value };
    exercises[exerciseIndex] = { ...exercises[exerciseIndex], sets_detail: sets };
    exercises = exercises;
    emit();
  }

  /**
   * What was done for this set last time, if anything, as placeholder text.
   *
   * Matched by **set type and its ordinal within that type**, not by position.
   * Position alone is wrong the moment last session began with a warm-up: set 1
   * of today's working block would offer the warm-up's 60 kg as "what you did",
   * and the tap-to-accept below would write it in. Suggesting a number far
   * under the working weight is not a small error — accepted once, it is what
   * the next session then suggests.
   */
  function lastSet(exercise: Exercise, setIndex: number): ExerciseSet | undefined {
    const id = exercise.catalog_id;
    if (!id) return undefined;
    const history = lastByCatalogId[id]?.sets;
    if (!history?.length) return undefined;

    const sets = exercise.sets_detail ?? [];
    const type = sets[setIndex]?.set_type ?? 'working';
    const ordinal = sets.slice(0, setIndex).filter((s) => s.set_type === type).length;
    const sameType = history.filter((s) => s.set_type === type);
    // Past the end means more sets than last time; the last one of that type is
    // the honest answer, and it is never a lighter set of a different kind.
    return sameType[ordinal] ?? sameType[sameType.length - 1];
  }

  function catalogEntry(exercise: Exercise): CatalogEntry | undefined {
    return catalog.find((c) => c.id === exercise.catalog_id);
  }

  // Volume counts working and failure sets; a warm-up is not the work.
  $: totalVolume = exercises.reduce(
    (sum, e) =>
      sum +
      (e.sets_detail ?? [])
        .filter((s) => s.set_type !== 'warmup')
        .reduce((v, s) => v + (s.weight_kg ?? 0) * (s.reps ?? 0), 0),
    0
  );
  $: totalSets = exercises.reduce(
    (n, e) => n + (e.sets_detail ?? []).filter((s) => s.set_type !== 'warmup').length,
    0
  );

  // Prefetch last-session numbers for anything already on the card (an edit).
  $: for (const e of exercises) if (e.catalog_id) void loadLast(e.catalog_id);
</script>

<div class="space-y-3">
  {#each exercises as exercise, i (i)}
    {@const entry = catalogEntry(exercise)}
    <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
      <div class="flex items-center gap-2">
        <span class="font-medium text-sm flex-1 truncate">{exercise.name}</span>
        {#if entry?.video_url}
          <a
            href={entry.video_url}
            target="_blank"
            rel="noopener noreferrer"
            title="How to do this"
            class="p-1 text-gray-400 hover:text-primary-500"
          >
            <ExternalLink size={14} />
          </a>
        {/if}
        <button
          type="button"
          title="Note for this session"
          class={clsx('p-1', noteOpen[i] || exercise.notes ? 'text-primary-500' : 'text-gray-400')}
          on:click={() => {
            noteOpen[i] = !noteOpen[i];
            noteOpen = noteOpen;
          }}
        >
          <StickyNote size={14} />
        </button>
        <button
          type="button"
          title="Remove exercise"
          class="p-1 text-gray-400 hover:text-red-500"
          on:click={() => removeExercise(i)}
        >
          <Trash2 size={14} />
        </button>
      </div>

      {#if noteOpen[i] || exercise.notes}
        <input
          type="text"
          bind:value={exercise.notes}
          on:change={emit}
          placeholder="How did it feel?"
          class="input text-xs py-1"
        />
      {/if}

      <!-- Header row, so the three number columns are not guesswork -->
      <div
        class="grid grid-cols-[1.25rem_1fr_1fr_2rem_2.5rem_1.25rem] gap-1 text-[10px] text-gray-400 px-0.5"
      >
        <span>#</span><span>{weightLabel}</span><span>reps</span><span class="text-center"
          >type</span
        ><span class="text-center">RPE</span><span></span>
      </div>

      {#each exercise.sets_detail ?? [] as set, j}
        {@const previous = lastSet(exercise, j)}
        <div class="grid grid-cols-[1.25rem_1fr_1fr_2rem_2.5rem_1.25rem] gap-1 items-center">
          <span class="text-xs text-gray-400 tabular-nums">{set.set_number}</span>
          <input
            type="number"
            step="any"
            inputmode="decimal"
            aria-label="Set {set.set_number} weight in {weightLabel}"
            value={toDisplay(set.weight_kg)}
            on:focus={() => acceptLast(i, j, 'weight_kg')}
            on:input={(e) => setWeight(i, j, e.currentTarget.value)}
            placeholder={previous?.weight_kg != null ? toDisplay(previous.weight_kg) : '—'}
            class="input py-1 text-sm tabular-nums"
          />
          <input
            type="number"
            inputmode="numeric"
            aria-label="Set {set.set_number} reps"
            bind:value={set.reps}
            on:focus={() => acceptLast(i, j, 'reps')}
            on:change={emit}
            placeholder={previous?.reps != null ? String(previous.reps) : '—'}
            class="input py-1 text-sm tabular-nums"
          />
          <button
            type="button"
            title={TYPE_TITLE[set.set_type]}
            aria-label="Set {set.set_number}: {TYPE_TITLE[set.set_type]}. Tap to change."
            on:click={() => cycleType(i, j)}
            class={clsx(
              'h-7 rounded text-xs font-semibold',
              set.set_type === 'warmup' && 'bg-amber-100 text-amber-700 dark:bg-amber-900/40',
              set.set_type === 'working' && 'bg-gray-100 text-gray-500 dark:bg-gray-700',
              set.set_type === 'failure' && 'bg-red-100 text-red-600 dark:bg-red-900/40'
            )}
          >
            {TYPE_LABEL[set.set_type]}
          </button>
          <input
            type="number"
            step="0.5"
            inputmode="decimal"
            aria-label="Set {set.set_number} RPE, 1 to 10"
            bind:value={set.rpe}
            on:change={emit}
            placeholder="—"
            class="input py-1 text-xs tabular-nums text-center"
          />
          <button
            type="button"
            title="Remove set"
            class="text-gray-300 hover:text-red-500"
            on:click={() => removeSet(i, j)}
          >
            <X size={12} />
          </button>
        </div>
      {/each}

      <button
        type="button"
        on:click={() => addSet(i)}
        class="w-full py-1.5 text-xs text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded"
      >
        + Add set
      </button>

      {#if lastByCatalogId[exercise.catalog_id ?? -1]?.date}
        <p class="text-[10px] text-gray-400">
          Last time · {lastByCatalogId[exercise.catalog_id ?? -1].date}
        </p>
      {/if}
    </div>
  {/each}

  {#if exercises.length === 0 && routines.length > 0}
    <!-- Only while empty: once you have started logging, replacing the list
         wholesale is far more likely to be a mistake than an intention. -->
    <div class="space-y-1">
      <p class="text-[11px] text-gray-400">Start from a routine</p>
      <div class="flex flex-wrap gap-2">
        {#each routines as routine}
          <button
            type="button"
            on:click={() => applyRoutine(routine)}
            class="px-3 py-1.5 text-xs rounded-full border border-gray-200 dark:border-gray-600 hover:border-primary-400 hover:text-primary-600"
          >
            {routine.name}
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <button
    type="button"
    on:click={openPicker}
    class="w-full py-2 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-500 hover:border-primary-400 hover:text-primary-600 flex items-center justify-center gap-1"
  >
    <Plus size={16} /> Add exercise
  </button>

  {#if exercises.length > 0}
    <p class="text-[11px] text-gray-400 text-right tabular-nums">
      {totalSets} working sets · {Math.round(
        weightFromMetric(totalVolume, unit)
      ).toLocaleString()}
      {weightLabel} volume
    </p>
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
        <input
          type="text"
          bind:value={pickerQuery}
          on:input={loadCatalog}
          placeholder="Search or add an exercise"
          class="input flex-1"
        />
        <button type="button" class="p-1 text-gray-400" on:click={() => (showPicker = false)}>
          <X size={18} />
        </button>
      </div>

      {#if catalogError}
        <p class="text-xs text-red-500">{catalogError}</p>
      {/if}

      <div class="flex-1 overflow-y-auto space-y-1">
        {#each catalog as entry}
          <button
            type="button"
            class="w-full text-left px-3 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
            on:click={() => addExercise(entry)}
          >
            <span class="flex-1 text-sm">{entry.name}</span>
            {#if entry.muscle_group}
              <span class="text-[10px] text-gray-400">{entry.muscle_group}</span>
            {/if}
          </button>
        {/each}

        {#if pickerQuery.trim() && !catalog.some((c) => c.name.toLowerCase() === pickerQuery.trim().toLowerCase())}
          <button
            type="button"
            disabled={creating}
            class="w-full text-left px-3 py-2 rounded text-sm text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20"
            on:click={createAndAdd}
          >
            + Add "{pickerQuery.trim()}" to the shared list
          </button>
        {/if}
      </div>

      <!-- The library is communal, so say so before someone adds to it. -->
      <p class="text-[10px] text-gray-400 border-t border-gray-200 dark:border-gray-700 pt-2">
        Exercises are shared — anything added here is available to everyone on this
        install. Add a video link or form notes on the
        <a href="/exercises" class="text-primary-500 hover:underline">Exercises</a> page.
      </p>
    </div>
  </div>
{/if}
