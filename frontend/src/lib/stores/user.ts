import { get, writable } from 'svelte/store';
import type { User } from '$lib/api/client';
import { db } from '$lib/db';

export const user = writable<User | null>(null);
export const userLoading = writable(true);

/**
 * Id of the account this browser tab is currently acting as, or undefined when
 * signed out.
 *
 * Everything that touches the local cache is scoped by this: a row is only
 * readable by the account that owns it, and a queued mutation is only pushed
 * under the account that made it. Reading the store synchronously (rather than
 * threading the id through every call site) keeps the guarantee in one place —
 * a new cache read cannot forget to scope itself.
 */
export function currentUserId(): number | undefined {
  return get(user)?.id ?? undefined;
}

// ── Cached identity ──────────────────────────────────────────────────────────
// The layout renders from this snapshot immediately instead of blocking first
// paint on /auth/me, then revalidates in the background.

const CACHED_USER_KEY = 'cachedUser';

export async function loadCachedUser(): Promise<User | null> {
  try {
    const entry = await db.settings.get(CACHED_USER_KEY);
    return (entry?.value as User | undefined) ?? null;
  } catch {
    return null;
  }
}

export async function cacheUser(value: User): Promise<void> {
  try {
    await db.settings.put({ key: CACHED_USER_KEY, value });
  } catch {
    // Best effort — a missing cache just means we block on the network again
  }
}

export async function clearCachedUser(): Promise<void> {
  try {
    await db.settings.delete(CACHED_USER_KEY);
  } catch {
    // Best effort
  }
}
