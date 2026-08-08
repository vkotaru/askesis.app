import { writable } from 'svelte/store';
import type { User } from '$lib/api/client';
import { db } from '$lib/db';

export const user = writable<User | null>(null);
export const userLoading = writable(true);

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
