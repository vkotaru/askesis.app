package app.askesis.data.model

import org.json.JSONArray
import org.json.JSONObject

/**
 * Structured payloads that ride inside the `exercisesJson` (activities) and `foodItemsJson`
 * (meals) string columns. Kept as plain JSON via org.json so they round-trip through the
 * Google Sheet unchanged and need no extra serialization dependency.
 */

data class ExerciseSet(
    val name: String,
    val sets: Int? = null,
    val reps: Int? = null,
    val weight: Double? = null,
)

data class MealFoodItem(
    val foodUid: String,
    val name: String,
    val quantity: Double,         // number of servings
    val calories: Double? = null, // per single serving
    val proteinG: Double? = null,
    val carbsG: Double? = null,
    val fatG: Double? = null,
)

data class MacroTotals(
    val calories: Double = 0.0,
    val proteinG: Double = 0.0,
    val carbsG: Double = 0.0,
    val fatG: Double = 0.0,
)

object Structured {

    // ── Exercises ──────────────────────────────────────────────────────────────
    fun encodeExercises(items: List<ExerciseSet>): String? {
        if (items.isEmpty()) return null
        val arr = JSONArray()
        items.forEach { e ->
            arr.put(
                JSONObject()
                    .put("name", e.name)
                    .putOpt("sets", e.sets)
                    .putOpt("reps", e.reps)
                    .putOpt("weight", e.weight)
            )
        }
        return arr.toString()
    }

    fun decodeExercises(json: String?): List<ExerciseSet> {
        if (json.isNullOrBlank()) return emptyList()
        return runCatching {
            val arr = JSONArray(json)
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                ExerciseSet(
                    name = o.optString("name"),
                    sets = o.optIntOrNull("sets"),
                    reps = o.optIntOrNull("reps"),
                    weight = o.optDoubleOrNull("weight"),
                )
            }
        }.getOrDefault(emptyList())
    }

    // ── Meal food items ─────────────────────────────────────────────────────────
    fun encodeFoodItems(items: List<MealFoodItem>): String? {
        if (items.isEmpty()) return null
        val arr = JSONArray()
        items.forEach { f ->
            arr.put(
                JSONObject()
                    .put("foodUid", f.foodUid)
                    .put("name", f.name)
                    .put("quantity", f.quantity)
                    .putOpt("calories", f.calories)
                    .putOpt("proteinG", f.proteinG)
                    .putOpt("carbsG", f.carbsG)
                    .putOpt("fatG", f.fatG)
            )
        }
        return arr.toString()
    }

    fun decodeFoodItems(json: String?): List<MealFoodItem> {
        if (json.isNullOrBlank()) return emptyList()
        return runCatching {
            val arr = JSONArray(json)
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                MealFoodItem(
                    foodUid = o.optString("foodUid"),
                    name = o.optString("name"),
                    quantity = o.optDouble("quantity", 1.0),
                    calories = o.optDoubleOrNull("calories"),
                    proteinG = o.optDoubleOrNull("proteinG"),
                    carbsG = o.optDoubleOrNull("carbsG"),
                    fatG = o.optDoubleOrNull("fatG"),
                )
            }
        }.getOrDefault(emptyList())
    }

    /** Sum per-serving macros × quantity across a meal's linked foods. */
    fun totals(items: List<MealFoodItem>): MacroTotals = MacroTotals(
        calories = items.sumOf { (it.calories ?: 0.0) * it.quantity },
        proteinG = items.sumOf { (it.proteinG ?: 0.0) * it.quantity },
        carbsG = items.sumOf { (it.carbsG ?: 0.0) * it.quantity },
        fatG = items.sumOf { (it.fatG ?: 0.0) * it.quantity },
    )

    private fun JSONObject.optIntOrNull(key: String): Int? =
        if (has(key) && !isNull(key)) optInt(key) else null

    private fun JSONObject.optDoubleOrNull(key: String): Double? =
        if (has(key) && !isNull(key)) optDouble(key) else null
}
