<script lang="ts">
  /**
   * The way into a workout: one tap if a session is already running, two if not.
   *
   * Sits at the top of the dashboard in strength mode. Routines appear as chips
   * rather than behind a menu because picking one is the common case and a menu
   * would make every workout cost an extra tap.
   */
  import { goto } from '$app/navigation';
  import { Play, Dumbbell } from 'lucide-svelte';
  import { offlineApi } from '$lib/stores/data';
  import type { Routine } from '$lib/api/client';
  import { liveSession, clockTick, startSession } from '$lib/stores/workout';

  let routines: Routine[] = [];
  let busy = false;

  // Cached, so this works in a gym — the routines page used to say "Routines
  // need a connection", and starting from one is the main path in.
  void (async () => {
    routines = await offlineApi.getRoutines();
  })();

  $: elapsed = $liveSession
    ? Math.max(0, Math.floor(($clockTick - new Date($liveSession.startedAt).getTime()) / 1000))
    : 0;
  $: mmss = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
  $: loggedSets = ($liveSession?.exercises ?? []).reduce(
    (n, e) => n + e.sets.filter((s) => s.state === 'logged').length,
    0
  );

  async function begin(routine: Routine | null) {
    if (busy) return;
    busy = true;
    try {
      await startSession({ routine, name: routine?.name ?? 'Workout' });
      await goto('/workout');
    } finally {
      busy = false;
    }
  }
</script>

<div class="card p-4">
  {#if $liveSession}
    <div class="flex items-center gap-3">
      <span class="relative flex h-2.5 w-2.5 shrink-0">
        <span
          class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"
        ></span>
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary-500"></span>
      </span>
      <div class="min-w-0 flex-1">
        <p class="font-semibold truncate">{$liveSession.name}</p>
        <p class="text-xs text-gray-400 tabular-nums">
          {mmss} · {loggedSets} set{loggedSets === 1 ? '' : 's'} logged
        </p>
      </div>
      <button type="button" class="btn-primary py-2.5 px-5" on:click={() => goto('/workout')}>
        Resume
      </button>
    </div>
  {:else}
    <div class="flex items-center gap-2 mb-3">
      <Dumbbell size={18} class="text-strength-500" />
      <h2 class="font-semibold">Train</h2>
    </div>

    <button
      type="button"
      disabled={busy}
      on:click={() => begin(null)}
      class="btn-primary w-full py-3.5 flex items-center justify-center gap-2 text-base"
    >
      <Play size={18} /> Start workout
    </button>

    {#if routines.length > 0}
      <p class="text-[11px] text-gray-400 mt-3 mb-1.5">Or start from a routine</p>
      <div class="flex flex-wrap gap-2">
        {#each routines as routine (routine.id)}
          <button
            type="button"
            disabled={busy}
            on:click={() => begin(routine)}
            class="px-3 py-2 text-xs rounded-full border border-gray-200 dark:border-gray-600 hover:border-primary-400 hover:text-primary-600 disabled:opacity-50"
          >
            {routine.name}
          </button>
        {/each}
      </div>
    {/if}
  {/if}
</div>
