/**
 * Auth-token storage and request helpers.
 *
 * Web: relies on the access_token cookie set by /auth/callback. No token to
 * persist or attach — fetch must send `credentials: 'include'`.
 *
 * Native (Capacitor): the token comes back via a deep link
 * (app.askesis.app://auth/callback#token=<jwt>) and lives in @capacitor/preferences.
 * Every API request sends `Authorization: Bearer <jwt>`.
 */
import { IS_NATIVE } from './config';

const TOKEN_KEY = 'askesis_jwt';

let cachedToken: string | null = null;

async function preferencesGet(key: string): Promise<string | null> {
  if (!IS_NATIVE) return null;
  try {
    const { Preferences } = await import('@capacitor/preferences');
    const { value } = await Preferences.get({ key });
    return value ?? null;
  } catch {
    return null;
  }
}

async function preferencesSet(key: string, value: string): Promise<void> {
  if (!IS_NATIVE) return;
  try {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.set({ key, value });
  } catch {
    // Best effort — if preferences aren't available we just lose the token.
  }
}

async function preferencesRemove(key: string): Promise<void> {
  if (!IS_NATIVE) return;
  try {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.remove({ key });
  } catch {
    // Ignore
  }
}

export async function getAuthToken(): Promise<string | null> {
  if (!IS_NATIVE) return null;
  if (cachedToken) return cachedToken;
  cachedToken = await preferencesGet(TOKEN_KEY);
  return cachedToken;
}

export async function setAuthToken(token: string): Promise<void> {
  cachedToken = token;
  await preferencesSet(TOKEN_KEY, token);
}

export async function clearAuthToken(): Promise<void> {
  cachedToken = null;
  await preferencesRemove(TOKEN_KEY);
}

/** Headers to add to every API request. Empty on web (cookie does the work). */
export async function authHeaders(): Promise<Record<string, string>> {
  if (!IS_NATIVE) return {};
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Ask the server for a fresh access token. On web, the new cookie is set
 * server-side; on native, we cache the returned token. Returns true on
 * success, false on failure (caller should treat as logged-out).
 */
let refreshInFlight: Promise<boolean> | null = null;

export async function tryRefreshToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async (): Promise<boolean> => {
    const { apiUrl } = await import('./config');
    try {
      const res = await fetch(apiUrl('/auth/refresh'), {
        method: 'POST',
        credentials: 'include',
        headers: await authHeaders(),
      });
      if (!res.ok) return false;
      if (IS_NATIVE) {
        const data = await res.json().catch(() => null);
        if (data?.access_token) {
          await setAuthToken(data.access_token as string);
        }
      }
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}
