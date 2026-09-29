/**
 * Set durations, as typed at a machine with one thumb.
 *
 * A held set is entered far more often as "45" or "1:30" than as a number of
 * seconds, so both are accepted and so is a trailing unit. The parse is
 * deliberately forgiving in one direction only: anything it cannot read
 * becomes `null` rather than a guess, because a wrong duration is recorded
 * history and an empty one is a visible blank.
 */

/** Longest a single set may be. Matches the API's `duration_seconds` bound. */
export const MAX_SET_SECONDS = 86400;

/**
 * `"45"` → 45 · `"1:30"` → 90 · `"2m"` → 120 · `"90s"` → 90.
 *
 * A bare number is seconds, not minutes: the common case is a plank, and
 * "30" meaning half an hour would be absurd on a set row.
 */
export function parseDuration(raw: string): number | null {
  const text = raw.trim().toLowerCase();
  if (!text) return null;

  if (text.includes(':')) {
    const [m, sec = ''] = text.split(':');
    const mins = parseInt(m || '0', 10);
    // A partially typed "1:" is minutes with no seconds yet, not a failure —
    // this runs on every keystroke.
    const secs = sec === '' ? 0 : parseInt(sec, 10);
    if (!isFinite(mins) || !isFinite(secs)) return null;
    return clamp(mins * 60 + secs);
  }

  const value = parseFloat(text);
  if (!isFinite(value)) return null;
  if (text.endsWith('m')) return clamp(Math.round(value * 60));
  if (text.endsWith('h')) return clamp(Math.round(value * 3600));
  return clamp(Math.round(value));
}

function clamp(seconds: number): number | null {
  if (seconds < 0) return null;
  return Math.min(seconds, MAX_SET_SECONDS);
}

/** `45` → `"45"` · `90` → `"1:30"`. Under a minute stays bare, as it was typed. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '';
  if (seconds < 60) return String(seconds);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * The same value, but for reading rather than editing.
 *
 * A bare "45" in a history chip beside a "12" from a rep-only movement is
 * ambiguous — both are plausible rep counts. The unit is added for display
 * only; the input keeps `formatDuration`, because typing "45s" back in is not
 * what anyone does.
 */
export function formatDurationLabel(seconds: number | null | undefined): string {
  if (seconds == null) return '';
  return seconds < 60 ? `${seconds}s` : formatDuration(seconds);
}
