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
