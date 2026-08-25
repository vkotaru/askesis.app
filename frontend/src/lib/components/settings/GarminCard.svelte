<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { RefreshCw, Watch, AlertTriangle, Clock, CheckCircle2 } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type GarminStatus } from '$lib/api/client';
  import { sync } from '$lib/sync';

  let status: GarminStatus | null = null;
  // Distinct from "status.enabled === false": this is "we could not ask".
  let unreachable = false;
  let starting = false;
  let actionError = '';
  let poll: ReturnType<typeof setInterval> | null = null;

  const LOGIN_CMD = 'docker compose exec app python scripts/garmin_sync.py --login';

  async function load() {
    try {
      status = await api.getGarminStatus();
      unreachable = false;
    } catch {
      // Offline, or a server that predates this endpoint. Either way there is
      // nothing truthful to show, and a stale "last synced 4h ago" would be a
      // worse answer than none.
      unreachable = true;
    }
    schedulePoll();
  }

  function schedulePoll() {
    const shouldPoll = !!status?.running;
    if (shouldPoll && !poll) {
      poll = setInterval(load, 3000);
    } else if (!shouldPoll && poll) {
      clearInterval(poll);
      poll = null;
      // A finished run has written rows the cache has never seen. Pull them in
      // rather than waiting for whatever revalidation happens to fire next,
      // otherwise you sync your watch and the app still shows blanks.
      if (lastSummaryTotal() > 0) sync();
    }
  }

  function lastSummaryTotal(): number {
    return Object.values(status?.last_run?.summary ?? {}).reduce((a, b) => a + b, 0);
  }

  async function syncNow() {
    starting = true;
    actionError = '';
    try {
      const res = await api.runGarminSync();
      if (!res.started) actionError = 'A sync is already running.';
    } catch (e) {
      actionError = e instanceof Error ? e.message : 'Could not start a sync.';
    } finally {
      starting = false;
      await load();
    }
  }

  function relative(iso: string): string {
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.round(hrs / 24)}d ago`;
  }

  // Only the counts that actually moved — a run that filled nothing should say
  // so plainly rather than printing a row of zeroes.
  const SUMMARY_LABELS: Record<string, [string, string]> = {
    daily_logs_filled: ['day filled', 'days filled'],
    daily_logs_created: ['day added', 'days added'],
    activities_created: ['activity added', 'activities added'],
    activities_updated: ['activity updated', 'activities updated'],
  };

  $: filled = Object.entries(status?.last_run?.summary ?? {})
    .filter(([key, n]) => n > 0 && key in SUMMARY_LABELS)
    .map(([key, n]) => `${n} ${SUMMARY_LABELS[key][n === 1 ? 0 : 1]}`);

  onMount(load);
  onDestroy(() => poll && clearInterval(poll));
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

  {#if unreachable}
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
              {relative(status.last_run.started_at)}
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
      disabled={starting || status.running || !status.configured || !status.is_owner}
    >
      <RefreshCw size={16} class={clsx(status.running && 'animate-spin')} />
      {status.running ? 'Syncing…' : 'Sync now'}
    </button>
  {/if}
</div>
