// Unit conversion utilities
// Data is stored in metric (km, cm, kg, ml), converted for display

import type { DistanceUnit, MeasurementUnit, WeightUnit, WaterUnit } from '$lib/api/client';

// Conversion factors
const KM_TO_MI = 0.621371;
const CM_TO_IN = 0.393701;
const KG_TO_LB = 2.20462;
const ML_TO_OZ = 0.033814;
const ML_TO_CUPS = 0.00422675;

// Distance (km <-> mi)
export function formatDistance(km: number | undefined | null, unit: DistanceUnit): string {
  if (km == null) return '—';
  if (unit === 'mi') {
    return `${(km * KM_TO_MI).toFixed(1)} mi`;
  }
  return `${km.toFixed(1)} km`;
}

export function distanceToMetric(value: number, unit: DistanceUnit): number {
  if (unit === 'mi') {
    return value / KM_TO_MI;
  }
  return value;
}

export function distanceFromMetric(km: number, unit: DistanceUnit): number {
  if (unit === 'mi') {
    return km * KM_TO_MI;
  }
  return km;
}

// Body measurements (cm <-> in)
export function formatMeasurement(cm: number | undefined | null, unit: MeasurementUnit): string {
  if (cm == null) return '—';
  if (unit === 'in') {
    return `${(cm * CM_TO_IN).toFixed(1)} in`;
  }
  return `${cm.toFixed(1)} cm`;
}

export function measurementToMetric(value: number, unit: MeasurementUnit): number {
  if (unit === 'in') {
    return value / CM_TO_IN;
  }
  return value;
}

export function measurementFromMetric(cm: number, unit: MeasurementUnit): number {
  if (unit === 'in') {
    return cm * CM_TO_IN;
  }
  return cm;
}

// Weight (kg <-> lb)
export function formatWeight(kg: number | undefined | null, unit: WeightUnit): string {
  if (kg == null) return '—';
  if (unit === 'lb') {
    return `${(kg * KG_TO_LB).toFixed(1)} lb`;
  }
  return `${kg.toFixed(1)} kg`;
}

export function weightToMetric(value: number, unit: WeightUnit): number {
  if (unit === 'lb') {
    return value / KG_TO_LB;
  }
  return value;
}

export function weightFromMetric(kg: number, unit: WeightUnit): number {
  if (unit === 'lb') {
    return kg * KG_TO_LB;
  }
  return kg;
}

// Water (ml <-> L, oz, cups)
export function formatWater(ml: number | undefined | null, unit: WaterUnit): string {
  if (ml == null) return '—';
  switch (unit) {
    case 'L':
      return `${(ml / 1000).toFixed(1)} L`;
    case 'oz':
      return `${(ml * ML_TO_OZ).toFixed(0)} oz`;
    case 'cups':
      return `${(ml * ML_TO_CUPS).toFixed(1)} cups`;
    default:
      return `${ml} ml`;
  }
}

export function waterToMetric(value: number, unit: WaterUnit): number {
  switch (unit) {
    case 'L':
      return value * 1000;
    case 'oz':
      return value / ML_TO_OZ;
    case 'cups':
      return value / ML_TO_CUPS;
    default:
      return value;
  }
}

export function waterFromMetric(ml: number, unit: WaterUnit): number {
  switch (unit) {
    case 'L':
      return ml / 1000;
    case 'oz':
      return ml * ML_TO_OZ;
    case 'cups':
      return ml * ML_TO_CUPS;
    default:
      return ml;
  }
}

// Unit labels for form inputs
export function getDistanceLabel(unit: DistanceUnit): string {
  return unit === 'mi' ? 'mi' : 'km';
}

export function getMeasurementLabel(unit: MeasurementUnit): string {
  return unit === 'in' ? 'in' : 'cm';
}

export function getWeightLabel(unit: WeightUnit): string {
  return unit === 'lb' ? 'lb' : 'kg';
}

export function getWaterLabel(unit: WaterUnit): string {
  return unit;
}
