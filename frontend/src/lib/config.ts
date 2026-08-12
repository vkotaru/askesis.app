/**
 * Runtime config shared by the API client and sync engine.
 *
 * There is only one client — the SvelteKit PWA — and it is always served from
 * the same origin as the API, so every request is same-origin and auth happens
 * via the access_token cookie set by `POST /auth/login` (or `POST
 * /auth/set-initial-password`).
 */

/**
 * Resolve an API path. Relative paths (`/api/x`) are returned unchanged because
 * the app is same-origin; absolute `http(s)://` URLs pass through untouched.
 */
export function apiUrl(path: string): string {
  return path;
}
