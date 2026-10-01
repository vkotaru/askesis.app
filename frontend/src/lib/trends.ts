/**
 * Long-range history: taking months of daily rows and making them readable.
 *
 * The dashboard answers "how is this week going". This answers "what has the
 * last six months looked like", and the difference is not the date range — it
 * is that a year of daily bars is about one pixel each on a phone, so anything
 * past a few months has to be rolled up before it can be drawn at all.
 *
 * Two rules do most of the work here, and both are already written down
 * elsewhere in this app because getting them wrong produced visible nonsense:
 *
 * 1. **Average over the days that have a figure, never over the calendar.**
 *    A week with two days logged totalling 4,400 calories is 2,200/day, not
 *    631. `NutritionChartCard` carries the same comment; this is the same bug
 *    one zoom level out, where it would be far harder to notice.
 *
 * 2. **A missing day is missing, not zero.** Nothing here invents a point for a
 *    day with no row. A gap in a weight line is the truth about that month.
 *
 * Everything is a pure function over `{date, value}` — no stores, no units, no
 * formatting. Values stay in whatever canonical unit the caller holds (kg, ml,
 * minutes); display conversion happens at the component, as it does everywhere
 * else in this app.
 */

export type RangeKey = '1m' | '3m' | '6m' | '1y' | 'all';
export type Granularity = 'day' | 'week' | 'month';

export const RANGES: { value: RangeKey; label: string; days: number | null }[] = [
  { value: '1m', label: '1M', days: 30 },
  { value: '3m', label: '3M', days: 92 },
  { value: '6m', label: '6M', days: 183 },
  { value: '1y', label: '1Y', days: 365 },
  { value: 'all', label: 'All', days: null },
];

/** One day that actually has a figure. Days without one are simply absent. */
export interface DayPoint {
  /** ISO `YYYY-MM-DD`. */
  date: string;
  value: number;
}

export interface Bucket {
  /** Sort key and identity. For a day it is the date. */
  key: string;
  /** What the axis says. Deliberately short — these are drawn at 9px. */
  label: string;
  /** First day in the bucket, for the tooltip's "week of" line. */
  start: string;
  /** The average over the days in this bucket that had a figure. */
  value: number;
  /** How many days that was. A one-day week average is worth knowing about. */
  days: number;
}

export interface Summary {
  average: number;
  min: number;
  max: number;
  /** Days with a figure. The honest denominator for everything above. */
  logged: number;
  /** Earliest and latest values, for the direction of travel. */
  first: number;
  last: number;
  /** last - first. Null when there is only one point, where it means nothing. */
  change: number | null;
}

const MS_DAY = 86_400_000;

/** `YYYY-MM-DD` without going through a Date, which would apply a timezone. */
function parseISO(date: string): Date {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')}`;
}

/** The Monday of this date's week. Weeks start Monday, like the dashboard's. */
function weekStart(d: Date): Date {
  const out = new Date(d);
  // getDay() is 0 for Sunday, which belongs to the week that began six days
  // earlier — the off-by-one that puts every Sunday in the wrong bucket.
  const shift = (out.getDay() + 6) % 7;
  out.setDate(out.getDate() - shift);
  return out;
}

export function cutoffFor(range: RangeKey, today = new Date()): string | null {
  const spec = RANGES.find((r) => r.value === range);
  if (!spec?.days) return null;
  const d = new Date(today);
  d.setDate(d.getDate() - spec.days);
  return toISO(d);
}

export function withinRange(points: DayPoint[], range: RangeKey, today = new Date()): DayPoint[] {
  const cutoff = cutoffFor(range, today);
  const inRange = cutoff ? points.filter((p) => p.date >= cutoff) : points.slice();
  return inRange.sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * How finely to draw, decided by the data's actual span rather than the range
 * asked for.
 *
 * "All" on three months of logging is three months, and should be drawn daily;
 * rolling it into weeks because the button said "All" would throw away detail
 * that fits on the screen perfectly well.
 */
export function granularityFor(points: DayPoint[]): Granularity {
  if (points.length < 2) return 'day';
  const span =
    (parseISO(points[points.length - 1].date).getTime() - parseISO(points[0].date).getTime()) /
      MS_DAY +
    1;
  // 100 rather than 92 so that "3M" stays daily: ninety-odd bars across a phone
  // is three pixels each, which still reads as a shape, and rolling the range
  // people use most into weekly averages would hide exactly the day-to-day
  // variation they opened it for.
  if (span <= 100) return 'day';
  if (span <= 500) return 'week';
  return 'month';
}

export function bucket(points: DayPoint[], granularity: Granularity): Bucket[] {
  if (granularity === 'day') {
    return points.map((p) => ({
      key: p.date,
      label: p.date.slice(5).replace('-', '/'),
      start: p.date,
      value: p.value,
      days: 1,
    }));
  }

  const groups = new Map<string, { start: string; total: number; days: number }>();
  for (const p of points) {
    const d = parseISO(p.date);
    const start = granularity === 'week' ? weekStart(d) : new Date(d.getFullYear(), d.getMonth(), 1);
    const key = toISO(start);
    const g = groups.get(key) ?? { start: key, total: 0, days: 0 };
    g.total += p.value;
    g.days += 1;
    groups.set(key, g);
  }

  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, g]) => {
      const d = parseISO(key);
      return {
        key,
        label:
          granularity === 'week'
            ? `${d.getDate()} ${months[d.getMonth()]}`
            : `${months[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`,
        start: g.start,
        // Rule 1. Dividing by 7 (or by the month's length) would report a week
        // with two entries as a fifth of what was actually eaten.
        value: g.total / g.days,
        days: g.days,
      };
    });
}

/** Stats over the DAYS, not the buckets: a quiet month must not outweigh a busy one. */
export function summarise(points: DayPoint[]): Summary | null {
  if (!points.length) return null;
  const values = points.map((p) => p.value);
  return {
    average: values.reduce((a, b) => a + b, 0) / values.length,
    min: Math.min(...values),
    max: Math.max(...values),
    logged: values.length,
    first: values[0],
    last: values[values.length - 1],
    change: values.length > 1 ? values[values.length - 1] - values[0] : null,
  };
}

/**
 * How many of the days in the window have a figure at all.
 *
 * Shown because every other number on the page is conditioned on it: "7.1 h
 * average" means something different over 142 nights than over 9.
 */
export function coverage(points: DayPoint[], range: RangeKey, today = new Date()): number | null {
  if (!points.length) return null;
  const cutoff = cutoffFor(range, today);
  const start = cutoff && cutoff > points[0].date ? cutoff : points[0].date;
  const span =
    Math.round((parseISO(toISO(today)).getTime() - parseISO(start).getTime()) / MS_DAY) + 1;
  return span > 0 ? span : null;
}
