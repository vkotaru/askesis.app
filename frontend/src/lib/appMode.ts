/**
 * What the app *is*, per account.
 *
 * Two people share this install and use it for different things: one tracks
 * nutrition, photos, race plans and training load; the other wants a gym logger
 * and nothing else. Rather than build a second app, an account picks a mode and
 * the shell shows only what that mode is about.
 *
 * **This file is the single definition.** The sidebar, the route guard and the
 * dashboard all read it, and they must agree — a nav item hidden while its page
 * still renders is a worse outcome than not hiding it at all, because it looks
 * like a bug rather than a choice.
 *
 * Nothing here deletes or hides *data*. A hidden section's rows stay in the
 * database, keep syncing, and reappear untouched the moment the mode changes
 * back. The setting is about what one person wants to look at, not about what
 * the app is allowed to store.
 */

export type AppMode = 'full' | 'strength';

export const APP_MODES: AppMode[] = ['full', 'strength'];

export interface ModeDefinition {
  value: AppMode;
  label: string;
  /** One line, shown under the label in Settings. */
  blurb: string;
  /**
   * Routes this mode shows. `null` means every route — the difference between
   * "everything" and "a long list that someone will forget to update when a
   * page is added". Only a restricted mode enumerates.
   */
  routes: string[] | null;
}

/**
 * Strength mode's sections, in nav order.
 *
 * Daily Log earns its place: body weight is standard in lifting apps, it is
 * what the weight trend chart feeds on, and Garmin fills the sleep and step
 * fields on the same row without anyone typing. Measurements, progress photos
 * and the calendar were considered and left out — the dashboard's five-week
 * grid already answers what the calendar did.
 */
const STRENGTH_ROUTES = [
  '/',
  '/daily-log',
  '/activities',
  '/routines',
  '/exercises',
  '/settings',
];

export const MODE_DEFINITIONS: ModeDefinition[] = [
  {
    value: 'full',
    label: 'Everything',
    blurb: 'Nutrition, activities, measurements, photos, training plans — the lot.',
    routes: null,
  },
  {
    value: 'strength',
    label: 'Strength only',
    blurb: 'A gym logger: workouts, routines, the exercise library and body weight.',
    routes: STRENGTH_ROUTES,
  },
];

export function modeDefinition(mode: AppMode | string | null | undefined): ModeDefinition {
  return MODE_DEFINITIONS.find((m) => m.value === mode) ?? MODE_DEFINITIONS[0];
}

/**
 * Is `path` visible in this mode?
 *
 * Prefix-matched below the root so that a detail route travels with its section
 * (`/activities/12` is part of `/activities`). `/` has to be compared exactly or
 * it would match every path and the restriction would silently do nothing.
 */
export function routeAllowed(mode: AppMode | string | null | undefined, path: string): boolean {
  const { routes } = modeDefinition(mode);
  if (routes === null) return true;
  return routes.some((r) => (r === '/' ? path === '/' : path === r || path.startsWith(`${r}/`)));
}

/**
 * The named parts a restricted mode keeps — dashboard cards *and* the sections
 * of the Settings page.
 *
 * Separate from `routes` because some pages are made of parts rather than being
 * one thing: the dashboard stays in strength mode but its nutrition summary
 * does not, and Settings stays but a daily calorie target on a gym logger is
 * just clutter with a number in it.
 *
 * An allow-list, so a part added later is hidden until someone decides it
 * belongs. The failure that way round is a missing card, which someone reports;
 * the other way round is a nutrition tracker quietly reappearing.
 */
const STRENGTH_PARTS = [
  // Dashboard
  'snapshot',
  'steps',
  'weight',
  'sleep',
  'recentActivities',
  'activityMonth',
  // Settings
  'stepTarget',
  'units',
  'appearance',
  'account',
];

export function partVisible(mode: AppMode | string | null | undefined, key: string): boolean {
  if (modeDefinition(mode).value !== 'strength') return true;
  return STRENGTH_PARTS.includes(key);
}
