package app.askesis.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Domain accent colors, ported from the web app's Tailwind palette (`tailwind.config.js`).
 * The website tints each metric/section with one of these (weight=rest/teal, sleep=strength/purple,
 * steps+water=cardio/blue, nutrition=amber, moods=mood scale). Icon badges use the color at low
 * alpha for their background so the same token works in light and dark mode.
 */
object Accent {
    // cardio (blue)
    val Cardio = Color(0xFF3B9AF4)
    val CardioSoft = Color(0xFF60B8F9)
    // strength (purple)
    val Strength = Color(0xFFA855F7)
    // nutrition (amber)
    val Nutrition = Color(0xFFF59E0B)
    val Nutrition600 = Color(0xFFD97706)
    // rest (teal)
    val Rest = Color(0xFF14B8A6)

    // mood scale (red → green)
    val Mood1 = Color(0xFFEF4444)
    val Mood2 = Color(0xFFF97316)
    val Mood3 = Color(0xFFEAB308)
    val Mood4 = Color(0xFF84CC16)
    val Mood5 = Color(0xFF22C55E)
}
