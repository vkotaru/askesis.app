<script lang="ts">
  /**
   * A workout is running, and you are looking at something else.
   *
   * Shown on every route except the workout screen itself, so navigating away —
   * to fix a typo in the shared exercise library, to log your body weight —
   * cannot lose the thread. Without it, minimising a session and then tapping
   * around leaves no evidence it exists until you happen to return to the
   * dashboard.
   *
   * Also the stale prompt. A session untouched for six hours is offered rather
   * than silently resumed, and it is never auto-finished or auto-discarded:
   * those sets exist in exactly one place on Earth, so the only thing allowed
   * to end a session is a person.
   */
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { clsx } from 'clsx';
  import { liveSession, clockTick, isStale, discardSession } from '$lib/stores/workout';

  /** Dismissed for this page load only — the session itself is untouched. */
  let staleDismissed = false;

  $: onWorkout = $page.url.pathname === '/workout';
  $: stale = $liveSession ? isStale($liveSession) : false;
  $: elapsed = $liveSession
    ? Math.max(0, Math.floor(($clockTick - new Date($liveSession.startedAt).getTime()) / 1000))
    : 0;
  $: mmss = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
  $: loggedSets = ($liveSession?.exercises ?? []).reduce(
    (n, e) => n + e.sets.filter((s) => s.state === 'logged').length,
    0
  );
  $: startedLabel = $liveSession
    ? new Date($liveSession.startedAt).toLocaleString(undefined, {
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '';

  async function discard() {
    if (
      !confirm(
        loggedSets > 0
          ? `Discard ${loggedSets} logged set${loggedSets === 1 ? '' : 's'}? This cannot be undone.`
          : 'Discard this workout?'
      )
    )
      return;
    await discardSession();
    staleDismissed = false;
  }
</script>

{#if $liveSession && !onWorkout}
  {#if stale && !staleDismissed}
    <!-- A prompt rather than a banner: an old session needs a decision, and
         quietly carrying it forward would eventually attach today's sets to a
         workout that started yesterday. -->
    <div class="fixed inset-0 z-[70] bg-black/50 flex items-end sm:items-center justify-center p-4">
      <div class="bg-white dark:bg-gray-800 w-full sm:max-w-sm rounded-2xl p-5 space-y-4">
        <div>
          <h2 class="font-semibold text-lg">Unfinished workout</h2>
          <p class="text-sm text-gray-500 mt-1">
            {startedLabel} · {$liveSession.name}
          </p>
          <p class="text-sm text-gray-500">
            {loggedSets} set{loggedSets === 1 ? '' : 's'} logged across
            {$liveSession.exercises.length} exercise{$liveSession.exercises.length === 1 ? '' : 's'}
          </p>
        </div>
        <!-- Saved to the day it STARTED, and said out loud, because that is the
             one thing about resuming an old session that would otherwise
             surprise someone. -->
        <button type="button" class="btn-primary w-full py-3" on:click={() => goto('/workout')}>
          Finish it
        </button>
        <button
          type="button"
          class="btn-secondary w-full py-3"
          on:click={() => (staleDismissed = true)}
        >
          Keep it open
        </button>
        <button type="button" class="w-full text-sm text-red-500 py-1" on:click={discard}>
          Discard
        </button>
      </div>
    </div>
  {/if}

  <button
    type="button"
    on:click={() => goto('/workout')}
    class={clsx(
      'w-full flex items-center gap-2 px-4 h-11 text-sm',
      'bg-primary-500 text-white hover:bg-primary-600 transition-colors'
    )}
  >
    <span class="relative flex h-2 w-2 shrink-0">
      <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"
      ></span>
      <span class="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
    </span>
    <span class="truncate font-medium">{$liveSession.name}</span>
    <span class="tabular-nums opacity-90">{mmss}</span>
    <span class="opacity-75">· {loggedSets} sets</span>
    <span class="ml-auto font-medium">Resume ›</span>
  </button>
{/if}
