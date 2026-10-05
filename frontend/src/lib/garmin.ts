/**
 * Garmin sync state, in one place and polled once.
 *
 * There are now two things on screen that start a sync and report on it — the
 * card in Settings and the button in the header — and before this module the
 * card owned all of it: the fetch, the three-second poller, the "is this button
 * allowed to be enabled" predicate, and the pull-the-new-rows-in call that
 * makes a finished sync actually show up. A second copy of that would be a
 * second poller hitting the same endpoint on the same schedule, and two
 * disagreeing answers to "can I sync right now".
 *
 * So: one store, one poller, refcounted by however many components are
 * watching. The components render it and nothing else.
 */
import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { api, type GarminStatus } from '$lib/api/client';
import { sync } from '$lib/sync';

export const garminStatus = writable<GarminStatus | null>(null);

/**
 * Distinct from `status.enabled === false`, and the distinction matters: this
 * is "we could not ask", where a stale "last synced 4h ago" would be a worse
 * answer than none at all.
 */
export const garminUnreachable = writable(false);

/** Set while a start request is in flight, before `running` has caught up. */
export const garminStarting = writable(false);

const POLL_MS = 3000;
let poll: ReturnType<typeof setInterval> | null = null;
let watchers = 0;

export async function refreshGarmin(): Promise<void> {
  if (!browser) return;
  try {
    const next = await api.getGarminStatus();
    const wasRunning = get(garminStatus)?.running ?? false;
    garminStatus.set(next);
    garminUnreachable.set(false);
    // A run that has just finished wrote rows this device has never seen. Pull
    // them rather than waiting for whatever revalidation happens to fire next —
    // otherwise you sync your watch and the app still shows blanks.
    if (wasRunning && !next.running && filledCount(next) > 0) void sync();
  } catch {
    garminUnreachable.set(true);
  }
  managePoll();
}

function managePoll(): void {
  const shouldPoll = watchers > 0 && (get(garminStatus)?.running ?? false);
  if (shouldPoll && !poll) {
    poll = setInterval(() => void refreshGarmin(), POLL_MS);
  } else if (!shouldPoll && poll) {
    clearInterval(poll);
    poll = null;
  }
}

/**
 * Call from `onMount`; call the returned function from `onDestroy`.
 *
 * Refcounted so the poller stops when the last watcher goes away. A component
 * that forgets to release leaves a request every three seconds running for the
 * life of the tab.
 */
export function watchGarmin(): () => void {
  watchers += 1;
  void refreshGarmin();
  return () => {
    watchers = Math.max(0, watchers - 1);
    managePoll();
  };
}

/** Returns an error message, or null when the sync started. */
export async function startGarminSync(): Promise<string | null> {
  garminStarting.set(true);
  try {
    const res = await api.runGarminSync();
    if (!res.started) return 'A sync is already running.';
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : 'Could not start a sync.';
  } finally {
    garminStarting.set(false);
    await refreshGarmin();
  }
}

/**
 * May this account start a sync right now?
 *
 * Four reasons it cannot, and they are different: nothing is configured, the
 * configured account is the other person's, one is already running, or we are
 * mid-request. A control that is merely greyed out with no explanation is worse
 * than one that is absent — see `garminReason`.
 */
export function canSyncNow(status: GarminStatus | null, starting: boolean): boolean {
  if (!status || starting) return false;
  return status.configured && status.is_owner && !status.running;
}

/** Why not, in one short clause, or null when it can. */
export function garminReason(status: GarminStatus | null): string | null {
  if (!status) return 'Checking…';
  if (status.running) return 'Syncing…';
  if (!status.configured) return 'Not connected';
  if (!status.is_owner) return "Connected to someone else's watch";
  if (status.rate_limited) return 'Garmin is rate-limiting';
  if (status.needs_reauth) return 'Needs a login on the server';
  return null;
}

//: Only the counts that actually moved — a run that filled nothing should say
//: so plainly rather than printing a row of zeroes.
export const SUMMARY_LABELS: Record<string, [string, string]> = {
  daily_logs_filled: ['day filled', 'days filled'],
  daily_logs_created: ['day added', 'days added'],
  activities_created: ['activity added', 'activities added'],
  activities_updated: ['activity updated', 'activities updated'],
};

export function filledCount(status: GarminStatus | null): number {
  return Object.values(status?.last_run?.summary ?? {}).reduce((a, b) => a + b, 0);
}

export function filledPhrases(status: GarminStatus | null): string[] {
  return Object.entries(status?.last_run?.summary ?? {})
    .filter(([key, n]) => n > 0 && key in SUMMARY_LABELS)
    .map(([key, n]) => `${n} ${SUMMARY_LABELS[key][n === 1 ? 0 : 1]}`);
}

export function relativeTime(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

/** True only when there is something a person could usefully tap. */
export const garminActionable = derived(garminStatus, ($s) => !!$s?.configured && !!$s?.is_owner);
