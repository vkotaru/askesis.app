/**
 * Cycling -> equivalent steps, by energy expenditure rather than a fudge factor.
 *
 * The naive approach is a constant ("150 steps per minute of cycling"). It is
 * wrong in a way that matters here: it undercounts a commute, because cycling
 * to work is ~6.8 METs while walking is ~3.5, so a minute on the bike costs
 * roughly twice what a minute of walking does. A flat rate also cannot tell a
 * grinding uphill commute from a freewheeling one.
 *
 * So: convert the ride to kilocalories, then convert kilocalories to the number
 * of walking steps that would have cost the same. Both halves come from the
 * 2011 Compendium of Physical Activities (Ainsworth et al., Med Sci Sports
 * Exerc 43(8):1575-81), the standard reference for activity energy costs.
 *
 *     kcal            = minutes x (MET x 3.5 x weight_kg / 200)
 *     equivalent_steps = kcal / kcal_per_walking_step
 *
 * A neat consequence, and the reason the weight argument is optional: when the
 * ride's calories are *computed* rather than measured, body weight appears in
 * both the numerator and the denominator and cancels exactly. Weight only
 * changes the answer when Garmin supplied a real calorie figure, which is the
 * case where we actually want it to.
 *
 * Worked example, 30-minute commute: 6.8 METs, 70 kg -> 250 kcal -> ~6,400
 * equivalent steps. The flat 150/min rule would have said 4,500.
 */

/** Walking, 5 km/h, moderate pace. Compendium code 17190. */
const WALK_MET = 3.5;

/**
 * Steps per minute at that pace. 5 km/h with a ~0.76 m stride is ~110 spm, and
 * it is what makes the derived figure (~0.039 kcal/step at 70 kg) agree with
 * the commonly published 0.038-0.043 kcal/step.
 */
const WALK_CADENCE_SPM = 110;

/** Used when a ride has no weight to work from. Cancels out unless calories were measured. */
const DEFAULT_WEIGHT_KG = 70;

/**
 * Bicycling MET by speed, from the 2011 Compendium. Speeds converted from the
 * source's mph bands. Ordered fastest-first so the first match wins.
 */
const BIKE_MET_BANDS: { minKmh: number; met: number; code: string }[] = [
  { minKmh: 32.2, met: 16.8, code: '01060' }, // >20 mph, racing
  { minKmh: 25.7, met: 12.0, code: '01050' }, // 16-19 mph, very fast
  { minKmh: 22.5, met: 10.0, code: '01040' }, // 14-15.9 mph, vigorous
  { minKmh: 19.3, met: 8.0, code: '01030' }, // 12-13.9 mph, moderate
  { minKmh: 16.1, met: 6.8, code: '01020' }, // 10-11.9 mph, light
  { minKmh: 0, met: 4.0, code: '01010' }, // <10 mph, leisure
];

/**
 * Compendium code 01011, "bicycling, to/from work, self selected pace".
 * The right default for a ride with a duration but no distance, which is what
 * a manually logged commute usually is.
 */
const COMMUTE_MET = 6.8;

/** Energy cost of one walking step for a given body weight. */
function kcalPerStep(weightKg: number): number {
  return (WALK_MET * 3.5 * weightKg) / 200 / WALK_CADENCE_SPM;
}

function metForSpeed(kmh: number): number {
  return (BIKE_MET_BANDS.find(b => kmh >= b.minKmh) ?? BIKE_MET_BANDS[BIKE_MET_BANDS.length - 1])
    .met;
}

export interface RideLike {
  duration_mins?: number | null;
  distance_km?: number | null;
  calories?: number | null;
}

/**
 * Equivalent steps for one ride. Returns 0 when there is nothing to go on —
 * a ride with neither a duration nor a calorie figure cannot be converted, and
 * inventing a number would be worse than showing none.
 *
 * Preference order is deliberate: a measured calorie figure beats anything we
 * can derive, a speed-derived MET beats a default, and the commute default is
 * the last resort.
 */
export function rideToSteps(ride: RideLike, weightKg?: number | null): number {
  const weight = weightKg && weightKg > 0 ? weightKg : DEFAULT_WEIGHT_KG;
  const mins = ride.duration_mins ?? 0;

  let kcal: number;
  if (ride.calories && ride.calories > 0) {
    // Measured by the device: strictly better than anything derived here.
    kcal = ride.calories;
  } else if (mins > 0) {
    const km = ride.distance_km ?? 0;
    const met = km > 0 ? metForSpeed(km / (mins / 60)) : COMMUTE_MET;
    kcal = mins * ((met * 3.5 * weight) / 200);
  } else {
    return 0;
  }

  return Math.round(kcal / kcalPerStep(weight));
}

/**
 * Sum the equivalent steps for a day's rides. Callers should pass only
 * activities already classified as cycling — this module deliberately does not
 * re-implement that; `disciplines.ts` owns it.
 */
export function ridesToSteps(rides: RideLike[], weightKg?: number | null): number {
  return rides.reduce((total, ride) => total + rideToSteps(ride, weightKg), 0);
}
