<script lang="ts">
  /**
   * The live workout screen.
   *
   * Everything here is shaped by where it is used: one hand, standing, 60–90
   * seconds between sets, possibly with chalk on your fingers. That drives three
   * decisions that look odd on a desktop and are not:
   *
   * - **The tick is the only real button on a set row**, and it gets 44px. It is
   *   the primary action of the whole app. Set type, RPE and delete moved off
   *   the row into a sheet — a 20px delete next to two number fields is a trap.
   * - **"Last time" is a column, not a placeholder.** A placeholder vanishes the
   *   moment you type, which is exactly when you want to compare against it.
   * - **A row is `planned` until ticked.** Numbers can be prefilled from last
   *   session because there is now a moment of confirmation; the old form had
   *   none, which is why it could only ever show them as hints.
   *
   * Two things this screen got wrong on a real phone, fixed here and worth not
   * reintroducing:
   *
   * - **The row must be able to shrink.** Every column was `1fr` and every
   *   input carried the app-wide `.input` padding, so a set row's *minimum*
   *   width exceeded a 360px screen. The page then scrolled sideways, which on
   *   a phone pans the visual viewport — so the fixed header and the nav rail
   *   appeared to slide off the edge, and the whole app read as broken. Columns
   *   are `minmax(0,1fr)` and the fields are `min-w-0` with compact padding.
   * - **Not every movement is weight and reps.** A plank asked for kilograms.
   *   Which fields a row shows now comes from the movement's `trackingType`,
   *   and it is fixable from inside the session, because that is where anyone
   *   notices it is wrong.
   */
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import {
    ChevronDown,
    Check,
    Plus,
    Search,
    X,
    StickyNote,
    Trash2,
    Timer,
    Minus,
    SlidersHorizontal,
  } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { settings } from '$lib/stores/settings';
  import { offlineApi } from '$lib/stores/data';
  import {
    weightFromMetric,
    weightToMetric,
    getWeightLabel,
    distanceFromMetric,
    distanceToMetric,
    getDistanceLabel,
  } from '$lib/utils/units';
  import { formatDuration, parseDuration } from '$lib/utils/duration';
  import { describeSet } from '$lib/utils/sets';
  import { syncErrors } from '$lib/sync';
  import type { CatalogEntry, LastSession, SetType, TrackingType } from '$lib/api/client';
  import type { DraftSet } from '$lib/db';
  import {
    liveSession,
    liveSessionLoaded,
    loadLiveSession,
    clockTick,
    addExercise,
    addSet,
    removeExercise,
    removeSet,
    updateSet,
    setSetType,
    setTrackingType,
    SET_TYPES,
    toggleLogged,
    setExerciseNotes,
    adjustRest,
    skipRest,
    discardSession,
    finishSession,
    sessionTotals,
    sessionDurationMins,
  } from '$lib/stores/workout';

  let showPicker = false;
  let pickerQuery = '';
  let catalog: CatalogEntry[] = [];
  let creating = false;
  let showFinish = false;
  let finishName = '';
  let finishNotes = '';
  /**
   * Off by default. Most sessions are not templates, and a Routines list that
   * grows by one every time you train stops being a list of routines.
   */
  let alsoSaveRoutine = false;
  let saving = false;
  let error = '';

  /** Which exercise has its row-sheet open, and for which set. */
  let sheet: { exerciseId: string; setId: string } | null = null;
  /** Which exercise has its own sheet open — the kind of set it takes. */
  let exerciseSheet: string | null = null;
  let noteFor: string | null = null;

  /**
   * The duration field is the only one whose display is not a function of the
   * stored value: "1:" parses to 60, and reformatting that to "1:00" mid-word
   * would move the caret and eat the next keystroke. So while a duration input
   * has focus its text is whatever was typed, and the model is written from it.
   */
  let durationFocus: string | null = null;
  let durationText = '';

  /** Last session per catalogue id. Read from the cache, so it works offline. */
  let history: Record<number, LastSession> = {};
  const requested = new Set<number>();

  $: unit = $settings.weight_unit;
  $: weightLabel = getWeightLabel(unit);
  $: distanceUnit = $settings.distance_unit;
  $: distanceLabel = getDistanceLabel(distanceUnit);
  $: totals = sessionTotals($liveSession);
  // The day the session STARTED, matching what finishSession writes — a workout
  // finished after midnight belongs to the day it happened.
  $: sessionDate = $liveSession
    ? new Date($liveSession.startedAt).toLocaleDateString(undefined, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
      })
    : '';

  // Redirect only once we KNOW there is no session. `liveSession` is null both
  // when nothing is running and before the draft has been read from Dexie, and
  // treating those alike bounced you out of a live workout on every reload —
  // the session was in the database the whole time.
  $: if ($liveSessionLoaded && $liveSession === null) void goto('/', { replaceState: true });

  // Elapsed values recompute on the store's tick, never from a local counter.
  $: elapsed = $liveSession
    ? Math.max(0, Math.floor(($clockTick - new Date($liveSession.startedAt).getTime()) / 1000))
    : 0;
  $: restLeft =
    $liveSession?.restEndsAt != null
      ? Math.round((new Date($liveSession.restEndsAt).getTime() - $clockTick) / 1000)
      : null;

  const mmss = (s: number) =>
    `${Math.floor(Math.abs(s) / 60)}:${String(Math.abs(s) % 60).padStart(2, '0')}`;

  $: for (const ex of $liveSession?.exercises ?? []) {
    if (ex.catalogId && !requested.has(ex.catalogId)) {
      requested.add(ex.catalogId);
      void loadHistory(ex.catalogId);
    }
  }

  async function loadHistory(id: number) {
    const last = await offlineApi.getLastSession(id);
    history = { ...history, [id]: last };
  }

  /**
   * What was done for this set last time.
   *
   * Matched by set type and its ordinal within that type, never by position:
   * if last session opened with a warm-up, position alone would offer that
   * lighter weight as set one of today's working block.
   */
  function lastFor(
    // Passed in, not closed over. Svelte tracks the dependencies it can SEE in
    // a template expression; a function that reaches for `history` internally
    // is invisible to it, so the column rendered "—" and never updated once the
    // cache resolved — the header two lines above it said "last 2026-09-22"
    // the whole time, from the same object.
    hist: Record<number, LastSession>,
    catalogId: number | null,
    sets: DraftSet[],
    index: number
  ) {
    if (!catalogId) return undefined;
    const past = hist[catalogId]?.sets;
    if (!past?.length) return undefined;
    const type = sets[index]?.setType ?? 'working';
    const ordinal = sets.slice(0, index).filter((s) => s.setType === type).length;
    const sameType = past.filter((s) => s.set_type === type);
    return sameType[ordinal] ?? sameType[sameType.length - 1];
  }

  const toDisplay = (kg: number | null) =>
    kg == null ? '' : String(Math.round(weightFromMetric(kg, unit) * 100) / 100);

  function onWeight(exId: string, setId: string, raw: string) {
    const v = parseFloat(raw);
    updateSet(exId, setId, {
      weightKg: isFinite(v) ? Math.round(weightToMetric(v, unit) * 1000) / 1000 : null,
    });
  }

  function onReps(exId: string, setId: string, raw: string) {
    const v = parseInt(raw);
    updateSet(exId, setId, { reps: isFinite(v) ? v : null });
  }

  function onDuration(exId: string, setId: string, raw: string) {
    durationText = raw;
    updateSet(exId, setId, { durationSeconds: parseDuration(raw) });
  }

  function durationValue(set: DraftSet): string {
    return durationFocus === set.draftId ? durationText : formatDuration(set.durationSeconds);
  }

  const distanceDisplay = (metres: number | null | undefined) =>
    metres == null
      ? ''
      : String(Math.round(distanceFromMetric(metres / 1000, distanceUnit) * 100) / 100);

  function onDistance(exId: string, setId: string, raw: string) {
    const v = parseFloat(raw);
    updateSet(exId, setId, {
      distanceM: isFinite(v) ? Math.round(distanceToMetric(v, distanceUnit) * 1000) : null,
    });
  }

  /** Missing on a draft older than the field, and on a movement not in the library. */
  const kindOf = (ex: { trackingType?: TrackingType | null }): TrackingType =>
    ex.trackingType ?? 'weight_reps';

  /**
   * The row's columns, per kind. `minmax(0, 1fr)` and not `1fr`: a bare `1fr`
   * refuses to shrink below its content's minimum width, which is what made
   * this screen wider than the phone it runs on.
   */
  const COLUMNS: Record<TrackingType, string> = {
    weight_reps: 'grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,1fr)_3.25rem_2.75rem]',
    reps: 'grid-cols-[2.5rem_minmax(0,1fr)_3.25rem_2.75rem]',
    time: 'grid-cols-[2.5rem_minmax(0,1fr)_3.25rem_2.75rem]',
    distance_time: 'grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,1fr)_3.25rem_2.75rem]',
  };

  const TRACKING_ORDER: TrackingType[] = ['weight_reps', 'reps', 'time', 'distance_time'];

  const TRACKING_LABELS: Record<TrackingType, string> = {
    weight_reps: 'Weight & reps',
    reps: 'Reps only',
    time: 'Time',
    distance_time: 'Distance & time',
  };

  const TRACKING_HINTS: Record<TrackingType, string> = {
    weight_reps: 'Leave the weight blank for bodyweight',
    reps: 'For movements nobody loads',
    time: 'Planks, stretches, skipping',
    distance_time: 'A machine, a run, a swim',
  };

  /**
   * Field styling, written out rather than reusing `.input`.
   *
   * `.input` carries `px-4`, which on a five-column row is 2rem of padding per
   * field before a digit is drawn — enough on its own to push the row wider
   * than a phone. `min-w-0` is the other half: without it a grid item refuses
   * to shrink below its content's minimum width no matter what the track says.
   */
  const cellClass =
    'w-full min-w-0 px-2 py-1.5 text-sm tabular-nums text-center rounded-lg border ' +
    'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 ' +
    'focus:border-primary-500 dark:focus:border-primary-400 focus:outline-none ' +
    'focus:ring-2 focus:ring-primary-200 dark:focus:ring-primary-800';
  const loggedClass = 'bg-primary-50 dark:bg-primary-900/20';

  /** The letter on the set chip. Working sets get none — they are the default. */
  const TYPE_PREFIX: Record<SetType, string> = {
    warmup: 'W',
    working: '',
    drop: 'D',
    failure: 'F',
    cooldown: 'C',
  };

  const TYPE_CHIP: Record<SetType, string> = {
    warmup: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    working: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300',
    drop: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
    failure: 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300',
    cooldown: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
  };

  /**
   * What "last time" reads as. Shared with the activity history and the
   * activity editor — three screens showing the same set must not each invent
   * their own sentence, which is how a plank came to read as "BW" in two of
   * them.
   */
  function lastLabel(kind: TrackingType, previous: LastSession['sets'][number] | undefined) {
    if (!previous) return '—';
    return describeSet(previous, { weight: unit, distance: distanceUnit }, kind);
  }

  async function openPicker() {
    showPicker = true;
    pickerQuery = '';
    catalog = await offlineApi.getCatalog();
  }

  async function searchCatalog() {
    catalog = await offlineApi.getCatalog(pickerQuery || undefined);
  }

  async function createAndAdd() {
    const name = pickerQuery.trim();
    if (!name || creating) return;
    creating = true;
    try {
      const entry = await offlineApi.createCatalogEntry({ name });
      addExercise(entry);
    } catch {
      // Offline, or it already exists. Log it by name so the set is not lost;
      // it just has no catalogue link, so no last-time numbers for now.
      addExercise({ id: null, name });
    } finally {
      creating = false;
      showPicker = false;
    }
  }

  function openFinish() {
    finishName = $liveSession?.name ?? 'Workout';
    showFinish = true;
  }

  async function save() {
    if (saving) return;
    saving = true;
    try {
      const { routineSaved } = await finishSession(finishName, finishNotes, {
        alsoSaveRoutine,
      });
      // Saving a routine needs a connection; the workout itself does not. If
      // only half of it landed, say so — through the toast, because we are
      // about to leave this screen and the Routines page being quietly empty
      // later is exactly the confusion this control exists to end.
      if (alsoSaveRoutine && !routineSaved) {
        syncErrors.set([
          `"${finishName}" was saved to Activities, but the routine needs a ` +
            `connection. Save it again from Routines when you're back online.`,
        ]);
        setTimeout(() => syncErrors.set([]), 12000);
      }
      await goto('/', { replaceState: true });
    } catch {
      error = 'Could not save the workout. Your sets are still here — try again.';
      saving = false;
    }
  }

  async function discard() {
    const n = totals.sets;
    if (
      !confirm(
        n > 0
          ? `Discard ${n} logged set${n === 1 ? '' : 's'}? This cannot be undone.`
          : 'Discard this workout?'
      )
    )
      return;
    await discardSession();
    await goto('/', { replaceState: true });
  }

  // Load the draft here too, not only from the root layout.
  //
  // Landing directly on this route — a reload mid-session, a bookmark, the
  // browser restoring tabs — must not depend on the layout having finished its
  // own startup first. Without this the screen could decide "no session" while
  // the draft sat in Dexie, and redirect out of a workout in progress. The
  // function is idempotent, so calling it from both places is safe.
  onMount(async () => {
    if (!$liveSessionLoaded) await loadLiveSession();
    if ($liveSession) finishName = $liveSession.name;
  });
</script>

<svelte:head><title>Workout · Askesis</title></svelte:head>

{#if $liveSession}
  <div class="pb-28">
    <!-- Header: elapsed time and the only way out that keeps the session. -->
    <div
      class="sticky top-0 z-30 -mx-3 px-3 md:-mx-8 md:px-8 py-3 bg-white/95 dark:bg-gray-900/95 backdrop-blur border-b border-gray-200 dark:border-gray-700 flex items-center gap-3"
    >
      <button
        type="button"
        on:click={() => goto('/')}
        aria-label="Minimise — the workout keeps running"
        class="p-1.5 -ml-1.5 text-gray-400 hover:text-gray-600"
      >
        <ChevronDown size={20} />
      </button>
      <div class="min-w-0 flex-1">
        <p class="font-semibold truncate leading-tight">{$liveSession.name}</p>
        <p class="text-xs text-gray-400 tabular-nums">
          {mmss(elapsed)} · {totals.sets} sets · {Math.round(
            weightFromMetric(totals.volumeKg, unit)
          ).toLocaleString()}
          {weightLabel}
        </p>
      </div>
      <button type="button" class="btn-primary py-1.5 px-4 text-sm" on:click={openFinish}>
        Finish
      </button>
    </div>

    {#if error}
      <p class="mt-3 text-sm text-red-500">{error}</p>
    {/if}

    <div class="space-y-3 mt-3">
      {#each $liveSession.exercises as exercise (exercise.draftId)}
        {@const last = exercise.catalogId ? history[exercise.catalogId] : undefined}
        {@const kind = kindOf(exercise)}
        <div class="card p-3 space-y-2">
          <div class="flex items-center gap-2">
            <div class="min-w-0 flex-1">
              <p class="font-medium text-sm truncate">{exercise.name}</p>
              <p class="text-[10px] text-gray-400 truncate">
                {TRACKING_LABELS[kindOf(exercise)]}{#if last?.date}&nbsp;· last {last.date}{/if}
              </p>
            </div>
            <!-- The fix for "this plank is asking me for kilograms", put where
                 that gets noticed: in the session, not in a settings page two
                 taps away that nobody opens with a bar in their hands. -->
            <button
              type="button"
              aria-label="How {exercise.name} is measured"
              class="p-2 text-gray-400 hover:text-primary-500"
              on:click={() => (exerciseSheet = exercise.draftId)}
            >
              <SlidersHorizontal size={16} />
            </button>
            <button
              type="button"
              aria-label="Note for this session"
              class={clsx(
                'p-2',
                noteFor === exercise.draftId || exercise.notes
                  ? 'text-primary-500'
                  : 'text-gray-400'
              )}
              on:click={() =>
                (noteFor = noteFor === exercise.draftId ? null : exercise.draftId)}
            >
              <StickyNote size={16} />
            </button>
            <button
              type="button"
              aria-label="Remove {exercise.name}"
              class="p-2 text-gray-400 hover:text-red-500"
              on:click={() => removeExercise(exercise.draftId)}
            >
              <Trash2 size={16} />
            </button>
          </div>

          {#if noteFor === exercise.draftId || exercise.notes}
            <input
              type="text"
              value={exercise.notes ?? ''}
              on:input={(e) => setExerciseNotes(exercise.draftId, e.currentTarget.value)}
              placeholder="How did it feel?"
              class="input text-xs py-1.5"
            />
          {/if}

          <!-- set# | (the fields this kind of movement has) | last time | tick -->
          <div class={clsx('grid gap-1 text-[10px] text-gray-400 px-0.5', COLUMNS[kind])}>
            <span>set</span>
            {#if kind === 'weight_reps'}
              <span>{weightLabel}</span><span>reps</span>
            {:else if kind === 'reps'}
              <span>reps</span>
            {:else if kind === 'time'}
              <span>time</span>
            {:else}
              <span>{distanceLabel}</span><span>time</span>
            {/if}
            <span class="text-center">last</span><span></span>
          </div>

          {#each exercise.sets as set, i (set.draftId)}
            {@const previous = lastFor(history, exercise.catalogId, exercise.sets, i)}
            {@const working = exercise.sets
              .slice(0, i + 1)
              .filter((s) => s.setType === set.setType).length}
            {@const logged = set.state === 'logged'}
            <div class={clsx('grid gap-1 items-center', COLUMNS[kind])}>
              <!-- Set type stays visible here even though its control lives in
                   the sheet: W1 for a warm-up, D1 for a drop set, plain numbers
                   for working sets, each counted within its own kind. The
                   chevron is the whole discoverability of the sheet — without
                   it this reads as a label, and "there is no way to delete a
                   set" is what people concluded. -->
              <button
                type="button"
                aria-label="Set {working}, {set.setType}. Tap to change its type or remove it."
                on:click={() => (sheet = { exerciseId: exercise.draftId, setId: set.draftId })}
                class={clsx(
                  'h-9 rounded text-[11px] font-semibold tabular-nums',
                  'flex items-center justify-center gap-px',
                  TYPE_CHIP[set.setType]
                )}
              >
                {TYPE_PREFIX[set.setType]}{working}<ChevronDown size={9} class="opacity-60" />
              </button>

              {#if kind === 'weight_reps'}
                <input
                  type="number"
                  step="any"
                  inputmode="decimal"
                  enterkeyhint="next"
                  aria-label="Set {working} weight in {weightLabel}"
                  value={toDisplay(set.weightKg)}
                  on:input={(e) => onWeight(exercise.draftId, set.draftId, e.currentTarget.value)}
                  placeholder={previous?.weight_kg != null ? toDisplay(previous.weight_kg) : '—'}
                  class={clsx(cellClass, logged && loggedClass)}
                />
                <input
                  type="number"
                  inputmode="numeric"
                  enterkeyhint="done"
                  aria-label="Set {working} reps"
                  value={set.reps ?? ''}
                  on:input={(e) => onReps(exercise.draftId, set.draftId, e.currentTarget.value)}
                  placeholder={previous?.reps != null ? String(previous.reps) : '—'}
                  class={clsx(cellClass, logged && loggedClass)}
                />
              {:else if kind === 'reps'}
                <input
                  type="number"
                  inputmode="numeric"
                  enterkeyhint="done"
                  aria-label="Set {working} reps"
                  value={set.reps ?? ''}
                  on:input={(e) => onReps(exercise.draftId, set.draftId, e.currentTarget.value)}
                  placeholder={previous?.reps != null ? String(previous.reps) : '—'}
                  class={clsx(cellClass, logged && loggedClass)}
                />
              {:else if kind === 'time'}
                <!-- text, not number: "1:30" is the natural way to type ninety
                     seconds and a number input will not accept the colon. -->
                <input
                  type="text"
                  inputmode="numeric"
                  enterkeyhint="done"
                  aria-label="Set {working} duration, seconds or m:ss"
                  value={durationValue(set)}
                  on:focus={() => {
                    durationFocus = set.draftId;
                    durationText = formatDuration(set.durationSeconds);
                  }}
                  on:blur={() => (durationFocus = null)}
                  on:input={(e) => onDuration(exercise.draftId, set.draftId, e.currentTarget.value)}
                  placeholder={formatDuration(previous?.duration_seconds) || 'm:ss'}
                  class={clsx(cellClass, logged && loggedClass)}
                />
              {:else}
                <input
                  type="number"
                  step="any"
                  inputmode="decimal"
                  enterkeyhint="next"
                  aria-label="Set {working} distance in {distanceLabel}"
                  value={distanceDisplay(set.distanceM)}
                  on:input={(e) => onDistance(exercise.draftId, set.draftId, e.currentTarget.value)}
                  placeholder={distanceDisplay(previous?.distance_m) || '—'}
                  class={clsx(cellClass, logged && loggedClass)}
                />
                <input
                  type="text"
                  inputmode="numeric"
                  enterkeyhint="done"
                  aria-label="Set {working} duration, seconds or m:ss"
                  value={durationValue(set)}
                  on:focus={() => {
                    durationFocus = set.draftId;
                    durationText = formatDuration(set.durationSeconds);
                  }}
                  on:blur={() => (durationFocus = null)}
                  on:input={(e) => onDuration(exercise.draftId, set.draftId, e.currentTarget.value)}
                  placeholder={formatDuration(previous?.duration_seconds) || 'm:ss'}
                  class={clsx(cellClass, logged && loggedClass)}
                />
              {/if}

              <!-- A column, not a placeholder: you compare against it while
                   typing, which is exactly when a placeholder disappears. -->
              <span class="text-[10px] text-gray-400 text-center tabular-nums leading-tight break-words">
                {lastLabel(kind, previous)}
              </span>

              <button
                type="button"
                aria-label={logged ? `Set ${working} logged. Tap to undo.` : `Log set ${working}`}
                on:click={() => toggleLogged(exercise.draftId, set.draftId)}
                class={clsx(
                  'h-11 rounded-lg flex items-center justify-center transition-colors',
                  logged
                    ? 'bg-primary-500 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-400 hover:bg-gray-200'
                )}
              >
                <Check size={18} />
              </button>
            </div>
          {/each}

          <!-- Removing the last set needs to be one obvious tap. The per-set
               sheet can remove any row, but it is behind the set chip, and a
               control you have to find is a control that does not exist. -->
          <div class="flex gap-1">
            <button
              type="button"
              on:click={() => addSet(exercise.draftId)}
              class="flex-1 py-2 text-xs text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded"
            >
              + Add set
            </button>
            {#if exercise.sets.length > 1}
              <button
                type="button"
                aria-label="Remove the last set of {exercise.name}"
                on:click={() =>
                  removeSet(
                    exercise.draftId,
                    exercise.sets[exercise.sets.length - 1].draftId
                  )}
                class="w-10 py-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded flex items-center justify-center"
              >
                <Minus size={14} />
              </button>
            {/if}
          </div>
        </div>
      {/each}

      <button
        type="button"
        on:click={openPicker}
        class="w-full py-3 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-500 hover:border-primary-400 hover:text-primary-600 flex items-center justify-center gap-1"
      >
        <Plus size={16} /> Add exercise
      </button>
    </div>
  </div>

  <!-- Rest bar. Docked, never modal: you correct the set you just logged while
       it runs, so it must not cover the rows. -->
  {#if restLeft !== null}
    <div
      class="fixed bottom-0 right-0 left-12 md:left-0 z-40 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700"
      style="padding-bottom: env(safe-area-inset-bottom);"
    >
      {#if restLeft > 0}
        <div class="h-1 bg-primary-100 dark:bg-primary-900/40">
          <div
            class="h-full bg-primary-500 transition-[width] duration-1000 ease-linear"
            style="width: {Math.min(100, Math.max(0, (restLeft / ($liveSession.restSecondsDefault || 1)) * 100))}%"
          ></div>
        </div>
      {/if}
      <div class="flex items-center gap-2 px-4 h-16">
        <Timer size={18} class={restLeft > 0 ? 'text-primary-500' : 'text-gray-400'} />
        {#if restLeft > 0}
          <span class="font-semibold tabular-nums text-lg w-16">{mmss(restLeft)}</span>
          <button type="button" class="btn-secondary py-1.5 px-3 text-xs" on:click={() => adjustRest(-15)}>
            −15
          </button>
          <button type="button" class="btn-secondary py-1.5 px-3 text-xs" on:click={() => adjustRest(15)}>
            +15
          </button>
          <button type="button" class="ml-auto text-sm text-gray-500 px-2 py-2" on:click={skipRest}>
            Skip
          </button>
        {:else}
          <!-- Counting up from zero, or vanishing, would both misreport what
               happened while you were not looking. -->
          <span class="text-sm text-gray-500">Rest over · {mmss(restLeft)} ago</span>
          <button type="button" class="ml-auto text-sm text-gray-500 px-2 py-2" on:click={skipRest}>
            Dismiss
          </button>
        {/if}
      </div>
    </div>
  {/if}
{/if}

<!-- Per-set sheet: the controls that do not belong under a thumb mid-set. -->
{#if sheet && $liveSession}
  {@const ex = $liveSession.exercises.find((e) => e.draftId === sheet?.exerciseId)}
  {@const st = ex?.sets.find((s) => s.draftId === sheet?.setId)}
  {#if ex && st}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="fixed inset-0 z-[80] bg-black/50 flex items-end sm:items-center justify-center"
      on:click={() => (sheet = null)}
    >
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div
        class="bg-white dark:bg-gray-800 w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-4 space-y-4"
        on:click|stopPropagation
        style="padding-bottom: calc(1rem + env(safe-area-inset-bottom));"
      >
        <div class="flex items-center gap-2">
          <h2 class="font-semibold flex-1">{ex.name}</h2>
          <button type="button" class="p-1 text-gray-400" on:click={() => (sheet = null)}>
            <X size={18} />
          </button>
        </div>

        <div>
          <span class="label">Set type</span>
          <!-- All five at once, not a cycle button. Cycling was tolerable at
               three kinds; at five, reaching "cool-down" costs four taps and
               passes through two states that each mean something. -->
          <div class="grid grid-cols-2 gap-1.5">
            {#each SET_TYPES as option (option.value)}
              <button
                type="button"
                on:click={() => setSetType(ex.draftId, st.draftId, option.value)}
                class={clsx(
                  'px-3 py-2.5 rounded-lg text-sm text-left border',
                  st.setType === option.value
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 font-medium'
                    : 'border-gray-200 dark:border-gray-600'
                )}
              >
                {option.label}
              </button>
            {/each}
          </div>
          <p class="text-[11px] text-gray-400 mt-1.5">
            {SET_TYPES.find((o) => o.value === st.setType)?.hint}
          </p>
        </div>

        <div>
          <label for="sheet-rpe" class="label">
            RPE <span class="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            id="sheet-rpe"
            type="number"
            step="0.5"
            min="1"
            max="10"
            inputmode="decimal"
            value={st.rpe ?? ''}
            on:input={(e) =>
              updateSet(ex.draftId, st.draftId, {
                rpe: e.currentTarget.value ? parseFloat(e.currentTarget.value) : null,
              })}
            class="input"
          />
        </div>

        <button
          type="button"
          class="w-full py-2.5 rounded-lg text-sm text-red-600 bg-red-50 dark:bg-red-900/20"
          on:click={() => {
            removeSet(ex.draftId, st.draftId);
            sheet = null;
          }}
        >
          Remove this set
        </button>
      </div>
    </div>
  {/if}
{/if}

<!-- Per-exercise sheet: what kind of set this movement takes. -->
{#if exerciseSheet && $liveSession}
  {@const ex = $liveSession.exercises.find((e) => e.draftId === exerciseSheet)}
  {#if ex}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="fixed inset-0 z-[80] bg-black/50 flex items-end sm:items-center justify-center"
      on:click={() => (exerciseSheet = null)}
    >
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div
        class="bg-white dark:bg-gray-800 w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-4 space-y-4"
        on:click|stopPropagation
        style="padding-bottom: calc(1rem + env(safe-area-inset-bottom));"
      >
        <div class="flex items-center gap-2">
          <h2 class="font-semibold flex-1 min-w-0 truncate">{ex.name}</h2>
          <button type="button" class="p-1 text-gray-400" on:click={() => (exerciseSheet = null)}>
            <X size={18} />
          </button>
        </div>

        <div>
          <span class="label">How it's measured</span>
          <div class="space-y-1.5">
            {#each TRACKING_ORDER as option (option)}
              <button
                type="button"
                on:click={() => setTrackingType(ex.draftId, option)}
                class={clsx(
                  'w-full px-3 py-2.5 rounded-lg text-left border',
                  kindOf(ex) === option
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-gray-200 dark:border-gray-600'
                )}
              >
                <span class="text-sm font-medium">{TRACKING_LABELS[option]}</span>
                <span class="block text-[11px] text-gray-400">{TRACKING_HINTS[option]}</span>
              </button>
            {/each}
          </div>
        </div>

        <!-- Said out loud, because it is the surprising half: this is a
             property of the movement, and the movement belongs to everyone on
             this install. Numbers already typed are kept either way. -->
        <p class="text-[11px] text-gray-400">
          {#if ex.catalogId}
            Saved for {ex.name} everywhere, not just today. Anything you have already
            typed stays on the row.
          {:else}
            This movement isn't in the shared list, so the change applies to today's
            session only.
          {/if}
        </p>
      </div>
    </div>
  {/if}
{/if}

<!-- Exercise picker -->
{#if showPicker}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="fixed inset-0 z-[80] bg-black/50 flex items-end sm:items-center justify-center"
    on:click={() => (showPicker = false)}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="bg-white dark:bg-gray-800 w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-4 space-y-3 max-h-[80dvh] flex flex-col"
      on:click|stopPropagation
      style="padding-bottom: calc(1rem + env(safe-area-inset-bottom));"
    >
      <div class="flex items-center gap-2">
        <Search size={16} class="text-gray-400" />
        <input
          bind:value={pickerQuery}
          on:input={searchCatalog}
          placeholder="Search or add an exercise"
          aria-label="Search exercises"
          class="input flex-1"
        />
        <button type="button" class="p-1 text-gray-400" on:click={() => (showPicker = false)}>
          <X size={18} />
        </button>
      </div>
      <div class="flex-1 overflow-y-auto space-y-1">
        {#each catalog as entry (entry.id)}
          <button
            type="button"
            class="w-full text-left px-3 py-3 rounded hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
            on:click={() => {
              addExercise(entry);
              showPicker = false;
            }}
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
            class="w-full text-left px-3 py-3 rounded text-sm text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20"
            on:click={createAndAdd}
          >
            + Add "{pickerQuery.trim()}" to the shared list
          </button>
        {/if}
      </div>
      <p class="text-[10px] text-gray-400 border-t border-gray-200 dark:border-gray-700 pt-2">
        Exercises are shared — anything added here is available to everyone on this install.
      </p>
    </div>
  </div>
{/if}

<!-- Finish -->
{#if showFinish && $liveSession}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="fixed inset-0 z-[80] bg-black/50 flex items-end sm:items-center justify-center"
    on:click={() => (showFinish = false)}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="bg-white dark:bg-gray-800 w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-4 space-y-4"
      on:click|stopPropagation
      style="padding-bottom: calc(1rem + env(safe-area-inset-bottom));"
    >
      <div class="flex items-center gap-2">
        <h2 class="font-semibold flex-1">Finish workout</h2>
        <button type="button" class="p-1 text-gray-400" on:click={() => (showFinish = false)}>
          <X size={18} />
        </button>
      </div>

      <div>
        <label for="finish-name" class="label">Name</label>
        <input id="finish-name" bind:value={finishName} class="input" />
        <!-- Said out loud because it was not obvious: naming the session names
             the ACTIVITY. It lands in Activities and on the calendar for the
             day it started. Nothing here has ever created a routine, and a name
             box on a finish screen reads like it might. -->
        <p class="text-[11px] text-gray-400 mt-1">
          Saved to Activities for {sessionDate}.
        </p>
      </div>

      {#if !$liveSession.routineId}
        <!-- Only offered when the session did not come from a routine: you
             already have that one, and a second copy under the same name is
             clutter, not a feature. -->
        <label class="flex items-start gap-2.5 cursor-pointer">
          <input type="checkbox" bind:checked={alsoSaveRoutine} class="mt-0.5 h-4 w-4" />
          <span class="text-sm">
            Also save as a routine
            <span class="block text-[11px] text-gray-400">
              Keeps the movements and the number of sets, so you can start this
              session again in one tap. Not the weights — those are meant to move.
            </span>
          </span>
        </label>
      {/if}

      <p class="text-sm text-gray-500">
        {sessionDurationMins($liveSession) ?? 0} min · {totals.sets} sets ·
        {Math.round(weightFromMetric(totals.volumeKg, unit)).toLocaleString()}
        {weightLabel}
      </p>

      {#if totals.emptyLogged > 0}
        <p class="text-xs text-amber-600 dark:text-amber-500">
          {totals.emptyLogged} ticked set{totals.emptyLogged === 1 ? ' has' : 's have'} no
          weight or reps, so {totals.emptyLogged === 1 ? 'it' : 'they'} won't be saved.
        </p>
      {/if}

      {#if totals.plannedRemaining > 0}
        <!-- Said plainly rather than saved quietly: a set nobody ticked is a set
             nobody did, and finding it in your history later is worse. -->
        <p class="text-xs text-amber-600 dark:text-amber-500">
          {totals.plannedRemaining} set{totals.plannedRemaining === 1 ? '' : 's'} were never
          logged. They won't be saved.
        </p>
      {/if}

      <div>
        <label for="finish-notes" class="label">
          How did it go? <span class="text-gray-400 font-normal">(optional)</span>
        </label>
        <input id="finish-notes" bind:value={finishNotes} class="input" />
      </div>

      <button type="button" class="btn-primary w-full py-3" disabled={saving} on:click={save}>
        {saving ? 'Saving…' : 'Save workout'}
      </button>
      <div class="flex justify-between">
        <button type="button" class="text-sm text-gray-500 py-2" on:click={() => (showFinish = false)}>
          Keep going
        </button>
        <button type="button" class="text-sm text-red-500 py-2" on:click={discard}>Discard</button>
      </div>
    </div>
  </div>
{/if}
