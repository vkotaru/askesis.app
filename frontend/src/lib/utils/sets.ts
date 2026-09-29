/**
 * How one logged set reads, in one place.
 *
 * There are three screens that show a set — the live logger's "last time"
 * column, the activity history, and the activity editor — and before this they
 * each built the string themselves from `weight_kg` and `reps` alone. So a
 * 45-second plank read as "BW" and a 5 km run read as "BW", which is the same
 * bug the `tracking_type` work exists to fix, in the two places nobody looked.
 *
 * `kind` is passed when the caller knows it (the logger, which holds the
 * movement) and inferred from the data when it does not (history, which holds
 * only the set). Inference is safe here because it decides *wording*, never
 * what gets stored.
 */
import type {
  DistanceUnit,
  ExerciseSet,
  TrackingType,
  WeightUnit,
} from '$lib/api/client';
import { formatDurationLabel } from '$lib/utils/duration';
import { distanceFromMetric, formatWeight, getDistanceLabel } from '$lib/utils/units';

type AnySet = Pick<ExerciseSet, 'weight_kg' | 'reps' | 'duration_seconds' | 'distance_m'>;

export function inferKind(set: AnySet): TrackingType {
  if (set.distance_m != null) return 'distance_time';
  if (set.duration_seconds != null && set.weight_kg == null && set.reps == null) return 'time';
  if (set.reps != null && set.weight_kg == null) return 'reps';
  return 'weight_reps';
}

export function describeSet(
  set: AnySet,
  units: { weight: WeightUnit; distance: DistanceUnit },
  kind?: TrackingType | null
): string {
  const k = kind ?? inferKind(set);

  if (k === 'time') return formatDurationLabel(set.duration_seconds) || '—';

  if (k === 'reps') return set.reps != null ? String(set.reps) : '—';

  if (k === 'distance_time') {
    const km = set.distance_m == null ? null : distanceFromMetric(set.distance_m / 1000, units.distance);
    const parts = [
      km == null ? null : `${Math.round(km * 100) / 100} ${getDistanceLabel(units.distance)}`,
      formatDurationLabel(set.duration_seconds) || null,
    ].filter(Boolean);
    return parts.join(' · ') || '—';
  }

  // weight_reps. A blank weight is bodyweight, which is a real answer and not
  // a missing one — that is why the column exists at all.
  if (set.weight_kg == null && set.reps == null) return '—';
  const weight = set.weight_kg != null ? formatWeight(set.weight_kg, units.weight) : 'BW';
  return set.reps != null ? `${weight} × ${set.reps}` : weight;
}
