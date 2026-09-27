// Shared activity icon configuration
// Used across activities, calendar, and shared dashboard

import {
  Activity,
  Dumbbell,
  Bike,
  Footprints,
  Heart,
  Flame,
  Timer,
  Mountain,
  Waves,
  Trophy,
} from 'lucide-svelte';

export interface ActivityIcon {
  value: string;
  label: string;
  icon: typeof Activity;
}

// Available icons for activity selection
export const ACTIVITY_ICONS: ActivityIcon[] = [
  { value: 'activity', label: 'Activity', icon: Activity },
  { value: 'dumbbell', label: 'Weights', icon: Dumbbell },
  { value: 'bike', label: 'Bike', icon: Bike },
  { value: 'footprints', label: 'Run/Walk', icon: Footprints },
  { value: 'heart', label: 'Heart', icon: Heart },
  { value: 'flame', label: 'HIIT', icon: Flame },
  { value: 'timer', label: 'Timer', icon: Timer },
  { value: 'mountain', label: 'Hike', icon: Mountain },
  { value: 'waves', label: 'Swim', icon: Waves },
  { value: 'trophy', label: 'Sports', icon: Trophy },
];

// Map icon name to component (for quick lookup)
export const ICON_MAP: Record<string, typeof Activity> = {
  activity: Activity,
  dumbbell: Dumbbell,
  bike: Bike,
  footprints: Footprints,
  heart: Heart,
  flame: Flame,
  timer: Timer,
  mountain: Mountain,
  waves: Waves,
  trophy: Trophy,
};

// Get icon component by name, with fallback based on activity type
export function getActivityIcon(
  iconName: string | null | undefined,
  activityType?: 'cardio' | 'strength'
): typeof Activity {
  if (iconName && ICON_MAP[iconName]) {
    return ICON_MAP[iconName];
  }
  // Default based on activity type
  return activityType === 'strength' ? Dumbbell : Activity;
}

// Legend icons for display (subset of most common)
export const LEGEND_ICONS: ActivityIcon[] = [
  { value: 'footprints', label: 'Run/Walk', icon: Footprints },
  { value: 'bike', label: 'Bike', icon: Bike },
  { value: 'dumbbell', label: 'Weights', icon: Dumbbell },
  { value: 'waves', label: 'Swim', icon: Waves },
  { value: 'mountain', label: 'Hike', icon: Mountain },
  { value: 'flame', label: 'HIIT', icon: Flame },
];


// ── Emoji fallback ───────────────────────────────────────────────────────────
//
// For an activity saved without an explicit icon, which is most of them: the
// picker is optional and nobody reaches for it while logging a workout. Matched
// on the name, which is why the keys include the phrasings people actually type
// ("leg day", "morning run") rather than a tidy taxonomy.
//
// Lived inline in the calendar page until the dashboard's month card needed the
// same fallback. One table, or the two views disagree about what a run looks
// like.

const ACTIVITY_EMOJIS: Record<string, string> = {
  // Cardio
  'run': '🏃',
  'running': '🏃',
  'morning run': '🏃',
  'evening run': '🏃',
  'jog': '🏃',
  'cycling': '🚴',
  'bike': '🚴',
  'biking': '🚴',
  'swimming': '🏊',
  'swim': '🏊',
  'hike': '🥾',
  'hiking': '🥾',
  'trail hike': '🥾',
  'walk': '🚶',
  'walking': '🚶',
  'evening walk': '🚶',
  'hiit': '🔥',
  'hiit session': '🔥',
  'cardio': '❤️',
  // Strength
  'strength': '💪',
  'upper body': '💪',
  'lower body': '🦵',
  'leg day': '🦵',
  'legs': '🦵',
  'core': '🧘',
  'abs': '🧘',
  'back': '💪',
  'chest': '💪',
  'arms': '💪',
  'shoulders': '💪',
  'full body': '🏋️',
  'weights': '🏋️',
  'yoga': '🧘',
  'stretching': '🤸',
};

export function getActivityEmoji(name: string, type: string): string {
  const lowerName = name.toLowerCase();

  // Check for exact or partial match
  for (const [key, emoji] of Object.entries(ACTIVITY_EMOJIS)) {
    if (lowerName.includes(key)) {
      return emoji;
    }
  }

  // Fallback based on type
  return type === 'cardio' ? '🏃' : '💪';
}
