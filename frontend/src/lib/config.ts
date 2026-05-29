/**
 * Runtime config shared by the API client and sync engine.
 *
 * On the web build, requests stay same-origin (empty API_BASE) and auth
 * happens via the access_token cookie set by /auth/callback.
 *
 * On the Capacitor (native) build, the app loads from a `capacitor://`
 * origin, so we need an absolute API_BASE pointing at the deployed
 * backend, plus bearer-token auth (cookies don't traverse origins).
 */
import { Capacitor } from '@capacitor/core';

function rawBase(): string {
  // Vite inlines import.meta.env.* at build time.
  const fromEnv = import.meta.env.VITE_API_BASE;
  if (typeof fromEnv === 'string' && fromEnv.length > 0) {
    return fromEnv.replace(/\/$/, '');
  }
  return '';
}

export const IS_NATIVE = Capacitor.isNativePlatform();
export const API_BASE = IS_NATIVE ? rawBase() : '';

/** Build a fully-qualified URL for an API path. Pass either `/api/x` or `https://...`. */
export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path}`;
}
