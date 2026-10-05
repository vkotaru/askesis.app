<script lang="ts">
  /**
   * The full Garmin panel: what it does, when it runs, how the last run went,
   * and the one-time login instructions when it needs them.
   *
   * The *state* lives in `$lib/garmin` because the header's sync button reads
   * the same thing — one poller, one "can I sync right now" predicate, one
   * phrasing of "3 days filled". This file is the rendering.
   */
  import { onMount, onDestroy } from 'svelte';
  import { RefreshCw, Watch, AlertTriangle, Clock, CheckCircle2 } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import {
    garminStatus,
    garminUnreachable,
    garminStarting,
    canSyncNow,
    filledPhrases,
    relativeTime,
    startGarminSync,
    watchGarmin,
  } from '$lib/garmin';

  const LOGIN_CMD = 'docker compose exec app python scripts/garmin_sync.py --login';

  let actionError = '';
  let release: (() => void) | null = null;

  $: status = $garminStatus;
  $: filled = filledPhrases(status);

  async function syncNow() {
    actionError = (await startGarminSync()) ?? '';
  }

  onMount(() => {
    release = watchGarmin();
  });
  onDestroy(() => release?.());
</script>

<div class="card p-6">
  <div class="flex items-center gap-2 mb-4">
    <Watch size={20} class="text-cardio-500" />
    <h2 class="text-lg font-semibold">Garmin Connect</h2>
    {#if status?.running}
      <span class="ml-auto flex items-center gap-1.5 text-sm text-cardio-500">
        <RefreshCw size={14} class="animate-spin" />
        Syncing…
      </span>
    {/if}
  </div>

  {#if $garminUnreachable}
    <p class="text-sm text-gray-500">
      Can't reach the server right now, so there's nothing to report.
    </p>
  {:else if !status}
    <p class="text-sm text-gray-400">Loading…</p>
  {:else}
    <p class="text-sm text-gray-500 mb-4">
      Fills in steps, sleep and water from your watch, and imports activities.
      It only ever fills blanks — anything you typed yourself is left alone.
    </p>

    {#if status.rate_limited}
      <div class="mb-4 p-3 rounded-lg bg-mood-3/10 border border-mood-3/30 text-sm">
        <div class="flex items-center gap-2 font-medium mb-1">
          <Clock size={14} class="text-mood-3" />
          Garmin is rate-limiting us
        </div>
        <p class="text-gray-500">
          Nothing to fix — this clears on its own. Don't log in again to try to
          force it; that's what turns a short block into a longer one.
        </p>
      </div>
    {:else if status.needs_reauth}
      <div class="mb-4 p-3 rounded-lg bg-mood-1/10 border border-mood-1/30 text-sm">
        <div class="flex items-center gap-2 font-medium mb-1">
          <AlertTriangle size={14} class="text-mood-1" />
          {status.configured ? 'The saved session stopped working' : 'Not connected yet'}
        </div>
        <p class="text-gray-500 mb-2">
          Connecting needs a one-time login with your MFA code, which happens on
          the server — your Garmin password is never sent to this app. Run:
        </p>
        <code class="block p-2 rounded bg-gray-100 dark:bg-gray-800 text-xs overflow-x-auto"
          >{LOGIN_CMD}</code
        >
      </div>
    {/if}

    <dl class="space-y-2 text-sm">
      <div class="flex justify-between gap-4">
        <dt class="text-gray-500">Nightly sync</dt>
        <dd class="text-right">
          {#if status.enabled && status.scheduled_hour !== null}
            {String(status.scheduled_hour).padStart(2, '0')}:17 {status.timezone}
            <span class="text-gray-400">· {status.lookback_days}-day window</span>
          {:else}
            <span class="text-gray-400">Off — set GARMIN_SYNC_ENABLED=true</span>
          {/if}
        </dd>
      </div>

      {#if status.sync_username}
        <div class="flex justify-between gap-4">
          <dt class="text-gray-500">Account</dt>
          <dd class={clsx('text-right', !status.is_owner && 'text-gray-400')}>
            {status.sync_username}
            {#if !status.is_owner}<span class="text-xs"> (not you)</span>{/if}
          </dd>
        </div>
      {/if}

      <div class="flex justify-between gap-4">
        <dt class="text-gray-500">Last run</dt>
        <dd class="text-right">
          {#if status.last_run}
            <span title={status.last_run.started_at}>
              {relativeTime(status.last_run.started_at)}
            </span>
            <span class="text-gray-400 text-xs">· {status.last_run.trigger}</span>
          {:else}
            <!-- Run state lives in memory, so a restart erases it. "Not since
                 the server started" is the honest phrasing; "never" would be a
                 stronger claim than we can make. -->
            <span class="text-gray-400">Not since the server started</span>
          {/if}
        </dd>
      </div>

      {#if status.last_run && !status.last_run.running}
        <div class="flex justify-between gap-4">
          <dt class="text-gray-500">Filled</dt>
          <dd class="text-right">
            {#if filled.length}
              <span class="inline-flex items-center gap-1.5">
                <CheckCircle2 size={13} class="text-primary-500" />
                {filled.join(', ')}
              </span>
            {:else if status.last_run.ok}
              <span class="text-gray-400">Nothing new</span>
            {:else}
              <span class="text-mood-1">Failed</span>
            {/if}
          </dd>
        </div>
      {/if}
    </dl>

    {#if status.last_run?.errors.length}
      <ul class="mt-3 space-y-1 text-xs text-mood-1">
        {#each status.last_run.errors as err}
          <li class="break-words">{err}</li>
        {/each}
      </ul>
    {/if}

    {#if actionError}
      <p class="mt-3 text-xs text-mood-1">{actionError}</p>
    {/if}

    <button
      type="button"
      class="btn-secondary w-full mt-4 flex items-center justify-center gap-2"
      on:click={syncNow}
      disabled={!canSyncNow(status, $garminStarting)}
    >
      <RefreshCw size={16} class={clsx(status.running && 'animate-spin')} />
      {status.running ? 'Syncing…' : 'Sync now'}
    </button>
  {/if}
</div>
