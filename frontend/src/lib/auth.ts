/**
 * Auth request helpers.
 *
 * The app relies on the access_token cookie set by /auth/callback. There is no
 * token to persist or attach — fetch just has to send `credentials: 'include'`.
 */

/**
 * Ask the server for a fresh access token. The new cookie is set server-side.
 * Returns true on success, false on failure (caller should treat as
 * logged-out).
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
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}
