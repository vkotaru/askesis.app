"""Unit conversion utilities for metric/imperial conversions.

All data is stored in canonical metric units:
- Distance: kilometers (km)
- Body measurements: centimeters (cm)
- Weight: kilograms (kg)
- Water/volume: milliliters (ml)

Conversions happen at API boundaries based on user preferences.
"""

from typing import Literal

# Conversion factors (multiply to convert)
CONVERSIONS = {
    # Distance
    "km_to_mi": 0.621371,
    "mi_to_km": 1.60934,
    # Length/measurements
    "cm_to_in": 0.393701,
    "in_to_cm": 2.54,
    # Weight
    "kg_to_lb": 2.20462,
    "lb_to_kg": 0.453592,
    # Volume
    "ml_to_L": 0.001,
    "L_to_ml": 1000,
    "ml_to_oz": 0.033814,
    "oz_to_ml": 29.5735,
    "ml_to_cups": 0.00422675,
    "cups_to_ml": 236.588,
}

# Unit type definitions
DistanceUnit = Literal["km", "mi"]
MeasurementUnit = Literal["cm", "in"]
WeightUnit = Literal["kg", "lb"]
WaterUnit = Literal["ml", "L", "oz", "cups"]


def convert(value: float | None, from_unit: str, to_unit: str) -> float | None:
    """Convert a value between units.

    Args:
        value: The numeric value to convert (None returns None)
        from_unit: Source unit
        to_unit: Target unit

    Returns:
        Converted value or None if input is None
    """
    if value is None:
        return None

    if from_unit == to_unit:
        return value

    key = f"{from_unit}_to_{to_unit}"
    if key in CONVERSIONS:
        return round(value * CONVERSIONS[key], 4)

    # Try reverse conversion
    reverse_key = f"{to_unit}_to_{from_unit}"
    if reverse_key in CONVERSIONS:
        return round(value / CONVERSIONS[reverse_key], 4)

    raise ValueError(f"Unknown conversion: {from_unit} to {to_unit}")


def to_metric_distance(value: float | None, unit: DistanceUnit) -> float | None:
    """Convert distance to kilometers for storage."""
    return convert(value, unit, "km")


def from_metric_distance(value: float | None, unit: DistanceUnit) -> float | None:
    """Convert distance from kilometers for display."""
    return convert(value, "km", unit)


def to_metric_measurement(value: float | None, unit: MeasurementUnit) -> float | None:
    """Convert body measurement to centimeters for storage."""
    return convert(value, unit, "cm")


def from_metric_measurement(value: float | None, unit: MeasurementUnit) -> float | None:
    """Convert body measurement from centimeters for display."""
    return convert(value, "cm", unit)


def to_metric_weight(value: float | None, unit: WeightUnit) -> float | None:
    """Convert weight to kilograms for storage."""
    return convert(value, unit, "kg")


def from_metric_weight(value: float | None, unit: WeightUnit) -> float | None:
    """Convert weight from kilograms for display."""
    return convert(value, "kg", unit)


def to_metric_water(value: float | None, unit: WaterUnit) -> float | None:
    """Convert water volume to milliliters for storage."""
    return convert(value, unit, "ml")


def from_metric_water(value: float | None, unit: WaterUnit) -> float | None:
    """Convert water volume from milliliters for display."""
    return convert(value, "ml", unit)


# Unit labels for display
UNIT_LABELS = {
    "km": "km",
    "mi": "mi",
    "cm": "cm",
    "in": "in",
    "kg": "kg",
    "lb": "lb",
    "ml": "ml",
    "L": "L",
    "oz": "oz",
    "cups": "cups",
}
