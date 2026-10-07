<script lang="ts">
  /**
   * Pull from the watch, without going to Settings first.
   *
   * The sync lived only on the Settings page, which is three taps and a scroll
   * from the dashboard — and it is the thing you reach for *because* the
   * dashboard is showing yesterday's steps. So it lives with the navigation:
   * in the icon rail on a phone, in the sidebar's list on a desktop. (It was
   * first in the phone header beside the sync dot, which is not where anyone
   * looks for an action — the request had been the side rail.)
   *
   * **It renders nothing when there is nothing to tap** — no watch configured,
   * or the configured one is the other person's; see `garminShown`. When it is
   * shown but cannot sync, a tap says why rather than doing nothing.
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
    garminShown,
    garminReason,
    canSyncNow,
    filledPhrases,
    startGarminSync,
    watchGarmin,
  } from '$lib/garmin';

  /** `rail`: the phone's 48px icon column. `sidebar`: a row in the desktop nav. */
  export let variant: 'rail' | 'sidebar' = 'rail';

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
    if (!enabled) {
      // Not disabled in the DOM on purpose: a disabled button swallows the tap,
      // and "nothing happens" is the one answer that explains nothing.
      if (!running) show(garminReason(status) ?? 'Garmin sync is unavailable');
      return;
    }
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

{#if $garminShown}
  <button
    type="button"
    on:click={go}
    aria-disabled={!enabled}
    title={running ? 'Syncing from Garmin…' : (garminReason(status) ?? 'Sync from Garmin now')}
    aria-label={running ? 'Syncing from Garmin' : 'Sync from Garmin now'}
    class={clsx(
      'flex-shrink-0 transition-colors',
      variant === 'rail'
        ? 'flex flex-col items-center justify-center w-9 h-9 rounded-xl'
        : 'w-full flex items-center gap-3 px-4 py-3 rounded-xl mb-1 font-medium',
      enabled
        ? 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
        : 'text-gray-300 dark:text-gray-600'
    )}
  >
    {#if running}
      <RefreshCw size={variant === 'rail' ? 18 : 20} class="animate-spin text-cardio-500" />
    {:else}
      <Watch size={variant === 'rail' ? 18 : 20} class={enabled ? 'text-cardio-500' : ''} />
    {/if}
    {#if variant === 'rail'}
      <span class="text-[8px] leading-none mt-0.5">{running ? 'Syncing' : 'Sync'}</span>
    {:else}
      <span>{running ? 'Syncing watch…' : 'Sync watch'}</span>
    {/if}
  </button>
{/if}

{#if message}
  <!-- Fixed rather than anchored to the button: the button is in a 48px rail
       on one breakpoint and a sidebar on the other, and a popover positioned
       against it would be clipped or off-screen in one of them. -->
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
