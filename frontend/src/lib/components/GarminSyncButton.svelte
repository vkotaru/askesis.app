<script lang="ts">
  /**
   * Pull from the watch, without going to Settings first.
   *
   * The sync lived only on the Settings page, which is three taps and a scroll
   * from the dashboard — and it is the thing you reach for *because* the
   * dashboard is showing yesterday's steps. So it sits beside the sync-status
   * dot instead, in the header on a phone and in the sidebar footer on a
   * desktop.
   *
   * **It renders nothing when there is nothing to tap** — no watch configured,
   * or the configured one is the other person's. A permanently greyed button in
   * the header would be a permanent question.
   *
   * All the state comes from `$lib/garmin`, which the Settings card also reads,
   * so the two cannot disagree about whether a sync is running and there is
   * still only one poller.
   */
  import { onMount, onDestroy } from 'svelte';
  import { RefreshCw, Watch } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import {
    garminStatus,
    garminStarting,
    garminActionable,
    canSyncNow,
    filledPhrases,
    startGarminSync,
    watchGarmin,
  } from '$lib/garmin';

  /** The sidebar footer has room for a word; the phone header does not. */
  export let compact = true;

  let release: (() => void) | null = null;
  let message = '';
  let messageTimer: ReturnType<typeof setTimeout> | null = null;

  $: status = $garminStatus;
  $: enabled = canSyncNow(status, $garminStarting);
  $: running = !!status?.running || $garminStarting;

  /**
   * Report the outcome, briefly.
   *
   * Keyed on a NEW `last_run.started_at`, not on watching `running` go from
   * true to false. A sync with no cached session fails in about four
   * milliseconds — faster than the status request that follows the POST — so
   * the running state is never observed at all, and an edge-triggered version
   * of this showed nothing whatsoever for the one case where feedback matters
   * most. Verified: tap, 4ms run, no spinner, no message, no way to tell the
   * tap had registered.
   *
   * A sync that quietly fills nothing is also indistinguishable from one that
   * failed, which is the other half of why this exists.
   */
  let awaiting: string | null = null;
  $: if (awaiting !== null && status?.last_run && !status.last_run.running) {
    const run = status.last_run;
    if (run.started_at !== awaiting || awaiting === '') {
      awaiting = null;
      const phrases = filledPhrases(status);
      // The server's error is worth showing verbatim here: the common one names
      // the command that fixes it.
      show(
        run.ok === false
          ? (run.errors[0] ?? 'Sync failed')
          : phrases.length
            ? phrases.join(', ')
            : 'Nothing new'
      );
    }
  }

  function show(text: string) {
    message = text;
    if (messageTimer) clearTimeout(messageTimer);
    messageTimer = setTimeout(() => (message = ''), 6000);
  }

  async function go(event: MouseEvent) {
    // The layout closes its menus on any window click.
    event.stopPropagation();
    if (!enabled) return;
    // Remembered before starting, so the reporter above can tell this run from
    // whatever was last on screen. '' stands for "there was no previous run",
    // which is distinct from "the previous run happens to have this timestamp".
    awaiting = status?.last_run?.started_at ?? '';
    const error = await startGarminSync();
    if (error) {
      awaiting = null;
      show(error);
    }
  }

  onMount(() => {
    release = watchGarmin();
  });
  onDestroy(() => {
    release?.();
    if (messageTimer) clearTimeout(messageTimer);
  });
</script>

{#if $garminActionable}
  <button
    type="button"
    on:click={go}
    disabled={!enabled}
    title={running ? 'Syncing from Garmin…' : 'Sync from Garmin now'}
    aria-label={running ? 'Syncing from Garmin' : 'Sync from Garmin now'}
    class={clsx(
      'relative flex items-center gap-1.5 rounded-lg transition-colors',
      compact ? 'p-2' : 'px-2 py-1 text-sm',
      enabled
        ? 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
        : 'text-gray-300 dark:text-gray-600'
    )}
  >
    {#if running}
      <RefreshCw size={compact ? 20 : 16} class="animate-spin text-cardio-500" />
    {:else}
      <Watch size={compact ? 20 : 16} />
    {/if}
    {#if !compact}<span>Sync watch</span>{/if}
  </button>
{/if}

{#if message}
  <!-- Fixed rather than anchored to the button: the button is in a header on
       one breakpoint and a sidebar footer on the other, and a popover
       positioned against it would be off-screen in one of them. -->
  <div
    class="fixed inset-x-0 bottom-4 z-[60] flex justify-center px-4 pointer-events-none"
    style="bottom: calc(1rem + env(safe-area-inset-bottom));"
    role="status"
  >
    <span
      class="rounded-2xl bg-gray-900/90 text-white text-xs px-3 py-2 shadow-lg pointer-events-auto max-w-full text-center break-words"
    >
      Garmin · {message}
    </span>
  </div>
{/if}
