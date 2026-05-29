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
