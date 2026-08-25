// What kind of training was that? — one answer, shared by everything that asks.
//
// The data does not make this easy. `activity_type` has exactly two values
// (cardio, strength), Garmin files yoga and pilates under strength, and swims,
// hikes and walks all arrive as cardio. So the type alone cannot answer the
// question the weekly plan asks, and the dashboard's existing name matching
// (isBikeActivity / isRunActivity in routes/+page.svelte) only ever covered
// run and bike.
//
// Order of evidence, weakest last:
//   1. the name — the only signal that survives hand entry, and Garmin puts the
//      discipline in it ("Mountain View Running", "Yoga")
//   2. the icon — set by the importer per Garmin typeKey, and chosen by hand in
//      the activity form
//   3. activity_type — a two-way split, so only ever a fallback
//
// A NEW discipline needs a row here and nothing else.

import { Dumbbell, Bike, Footprints, Waves, Mountain, PersonStanding, Flower2, Activity } from 'lucide-svelte';
import type { Activity as ActivityType } from '$lib/api/client';

export type DisciplineKey =
  | 'run'
  | 'bike'
  | 'strength'
  | 'calisthenics'
  | 'stretch'
  | 'swim'
  | 'hike';

export interface Discipline {
  key: DisciplineKey;
  label: string;
  icon: typeof Activity;
  /** Tailwind text colour, matching the palette the other cards use. */
  color: string;
  /** Lowercased substrings tried against the activity name. */
  names: string[];
  /** Icon values (activities.icon) that imply this discipline. */
  icons: string[];
}

// Order matters: the first match wins. Calisthenics is listed before strength
// because "calisthenics strength" should read as calisthenics, and "push ups"
// should not be swallowed by a generic strength match.
export const DISCIPLINES: Discipline[] = [
  {
    key: 'calisthenics',
    label: 'Calisthenics',
    icon: PersonStanding,
    color: 'text-accent-500',
    names: ['calisthenic', 'bodyweight', 'body weight', 'pull up', 'pull-up', 'push up', 'push-up', 'dips', 'bar work'],
    icons: [],
  },
  {
    key: 'stretch',
    label: 'Stretching',
    // Not PersonStanding — calisthenics already uses it, and two identical
    // glyphs in a row of icons defeats the point of the row.
    icon: Flower2,
    color: 'text-mood-4',
    names: ['stretch', 'yoga', 'pilates', 'mobility', 'flexibility', 'foam roll'],
    icons: ['stretch'],
  },
  {
    key: 'swim',
    label: 'Swim',
    icon: Waves,
    color: 'text-cardio-400',
    names: ['swim', 'pool'],
    icons: ['waves'],
  },
  {
    key: 'hike',
    label: 'Hike / Walk',
    icon: Mountain,
    color: 'text-rest-500',
    names: ['hike', 'hiking', 'walk', 'walking', 'trek'],
    icons: ['mountain'],
  },
  {
    key: 'bike',
    label: 'Bike',
    icon: Bike,
    color: 'text-cardio-500',
    names: ['bike', 'biking', 'cycling', 'cycle', 'ride', 'spin'],
    icons: ['bike'],
  },
  {
    key: 'run',
    label: 'Run',
    icon: Footprints,
    color: 'text-primary-500',
    names: ['run', 'running', 'jog', 'jogging', 'treadmill'],
    icons: ['footprints'],
  },
  {
    key: 'strength',
    label: 'Strength',
    icon: Dumbbell,
    color: 'text-strength-500',
    names: ['strength', 'weights', 'lifting', 'gym', 'upper body', 'lower body', 'leg day', 'legs', 'chest', 'back', 'arms', 'shoulders', 'core', 'abs', 'full body'],
    icons: ['dumbbell'],
  },
];

export const DISCIPLINE_BY_KEY: Record<string, Discipline> = Object.fromEntries(
  DISCIPLINES.map((d) => [d.key, d])
);

/** Which discipline is this? `null` when nothing matches — better than guessing. */
export function classify(activity: Pick<ActivityType, 'name' | 'icon' | 'activity_type'>): DisciplineKey | null {
  const name = (activity.name || '').toLowerCase();

  for (const d of DISCIPLINES) {
    if (d.names.some((n) => name.includes(n))) return d.key;
  }
  if (activity.icon) {
    for (const d of DISCIPLINES) {
      if (d.icons.includes(activity.icon)) return d.key;
    }
  }
  // Last resort. 'cardio' is deliberately left unresolved rather than assumed
  // to be a run: it covers swims, hikes and rides too, so a guess here would
  // light up the wrong slot in the weekly plan.
  if (activity.activity_type === 'strength') return 'strength';
  return null;
}

/** Total distance in km for one discipline over the given activities. */
export function distanceFor(activities: ActivityType[], key: DisciplineKey): number {
  return activities
    .filter((a) => a.distance_km && classify(a) === key)
    .reduce((sum, a) => sum + (a.distance_km || 0), 0);
}

/** The discipline keys with at least one activity in the list. */
export function completedDisciplines(activities: ActivityType[]): Set<DisciplineKey> {
  const done = new Set<DisciplineKey>();
  for (const a of activities) {
    const key = classify(a);
    if (key) done.add(key);
  }
  return done;
}

/** Parse the comma-separated plan stored in user_settings. */
export function parsePlan(raw: string | null | undefined): DisciplineKey[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter((s): s is DisciplineKey => s in DISCIPLINE_BY_KEY);
}
