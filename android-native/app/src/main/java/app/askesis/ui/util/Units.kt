package app.askesis.ui.util

/**
 * Unit conversion + display helpers, ported 1:1 from the web app's
 * `frontend/src/lib/utils/units.ts`. Data is always stored in metric (km, cm, kg, ml)
 * and converted to the user's preferred unit only for display/input — exactly like the website.
 */

private const val KM_TO_MI = 0.621371
private const val CM_TO_IN = 0.393701
private const val KG_TO_LB = 2.20462
private const val ML_TO_OZ = 0.033814
private const val ML_TO_CUPS = 0.00422675

private fun Double.fixed(decimals: Int): String = "%.${decimals}f".format(this)

// ── Distance (km <-> mi) ──
fun formatDistance(km: Double?, unit: String): String {
    if (km == null) return "—"
    return if (unit == "mi") "${(km * KM_TO_MI).fixed(2)} mi" else "${km.fixed(2)} km"
}

fun distanceToMetric(value: Double, unit: String): Double = if (unit == "mi") value / KM_TO_MI else value
fun distanceFromMetric(km: Double, unit: String): Double = if (unit == "mi") km * KM_TO_MI else km
fun distanceLabel(unit: String): String = if (unit == "mi") "mi" else "km"

// ── Body measurements (cm <-> in) ──
fun formatMeasurement(cm: Double?, unit: String): String {
    if (cm == null) return "—"
    return if (unit == "in") "${(cm * CM_TO_IN).fixed(2)} in" else "${cm.fixed(2)} cm"
}

fun measurementToMetric(value: Double, unit: String): Double = if (unit == "in") value / CM_TO_IN else value
fun measurementFromMetric(cm: Double, unit: String): Double = if (unit == "in") cm * CM_TO_IN else cm
fun measurementLabel(unit: String): String = if (unit == "in") "in" else "cm"

// ── Weight (kg <-> lb) ──
fun formatWeight(kg: Double?, unit: String): String {
    if (kg == null) return "—"
    return if (unit == "lb") "${(kg * KG_TO_LB).fixed(2)} lb" else "${kg.fixed(2)} kg"
}

fun weightToMetric(value: Double, unit: String): Double = if (unit == "lb") value / KG_TO_LB else value
fun weightFromMetric(kg: Double, unit: String): Double = if (unit == "lb") kg * KG_TO_LB else kg
fun weightLabel(unit: String): String = if (unit == "lb") "lb" else "kg"

// ── Water (ml <-> L, oz, cups) ──
fun formatWater(ml: Int?, unit: String): String {
    if (ml == null) return "—"
    return when (unit) {
        "L" -> "${(ml / 1000.0).fixed(1)} L"
        "oz" -> "${(ml * ML_TO_OZ).fixed(0)} oz"
        "cups" -> "${(ml * ML_TO_CUPS).fixed(1)} cups"
        else -> "$ml ml"
    }
}

fun waterToMetric(value: Double, unit: String): Int = when (unit) {
    "L" -> (value * 1000).toInt()
    "oz" -> (value / ML_TO_OZ).toInt()
    "cups" -> (value / ML_TO_CUPS).toInt()
    else -> value.toInt()
}

fun waterFromMetric(ml: Int, unit: String): Double = when (unit) {
    "L" -> ml / 1000.0
    "oz" -> ml * ML_TO_OZ
    "cups" -> ml * ML_TO_CUPS
    else -> ml.toDouble()
}

fun waterLabel(unit: String): String = unit

/**
 * Format a metric value as the user's unit for an *editable* field (no unit suffix, blank for null).
 * Display rounding keeps full precision in storage; we only round what's shown so editing lb/in/mi
 * doesn't surface long floating-point tails. Whole numbers render without a trailing ".0".
 */
fun editValue(converted: Double?): String {
    if (converted == null) return ""
    val rounded = (converted * 100).toLong() / 100.0
    return if (rounded == rounded.toLong().toDouble()) rounded.toLong().toString() else rounded.toString()
}
