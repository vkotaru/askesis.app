package app.askesis.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * Ported from the web app's design system (app.css / tailwind.config.js): each scheme
 * swaps only the primary/accent hues, while the neutrals stay constant — a near-white
 * page with white cards and dark slate text in light mode (the web app's `surface-light`
 * + `.card` look), mirrored to near-black in dark mode.
 */
private data class Palette(val primary: Color, val accent: Color)

private val schemes = mapOf(
    "forest" to Palette(Color(0xFF2D7050), Color(0xFFE44D2E)),
    "ocean" to Palette(Color(0xFF257CE9), Color(0xFF0D9488)),
    "sunset" to Palette(Color(0xFFEA580C), Color(0xFFDB2777)),
    "lavender" to Palette(Color(0xFF9333EA), Color(0xFFE11D48)),
    "slate" to Palette(Color(0xFF475569), Color(0xFF2563EB)),
)

// ── Neutral tokens (shared by every scheme) ──────────────────────────────────
private val LightBackground = Color(0xFFFAFAFA)   // surface-light
private val LightCard = Color(0xFFFFFFFF)         // .card → bg-white
private val LightVariant = Color(0xFFF3F4F6)      // gray-100 (chips, tracks)
private val LightOnSurface = Color(0xFF111827)    // gray-900
private val LightOnVariant = Color(0xFF4B5563)    // gray-600
private val LightOutline = Color(0xFFE5E7EB)      // gray-200

private val DarkBackground = Color(0xFF1A1A1A)    // surface-dark
private val DarkCard = Color(0xFF1F2937)          // gray-800
private val DarkVariant = Color(0xFF374151)       // gray-700
private val DarkOnSurface = Color(0xFFF3F4F6)     // gray-100
private val DarkOnVariant = Color(0xFF9CA3AF)     // gray-400
private val DarkOutline = Color(0xFF374151)

private fun lightScheme(p: Palette): ColorScheme = lightColorScheme(
    primary = p.primary,
    onPrimary = Color.White,
    primaryContainer = p.primary.copy(alpha = 0.14f).compositeOverWhite(),
    onPrimaryContainer = p.primary,
    secondary = p.primary,
    onSecondary = Color.White,
    // NavigationBar's selected pill uses secondaryContainer — tint it with the brand.
    secondaryContainer = p.primary.copy(alpha = 0.16f).compositeOverWhite(),
    onSecondaryContainer = p.primary,
    tertiary = p.accent,
    onTertiary = Color.White,
    background = LightBackground,
    onBackground = LightOnSurface,
    surface = LightCard,
    onSurface = LightOnSurface,
    surfaceVariant = LightVariant,
    onSurfaceVariant = LightOnVariant,
    surfaceContainerLowest = LightCard,
    surfaceContainerLow = LightCard,
    surfaceContainer = LightCard,
    surfaceContainerHigh = LightCard,
    surfaceContainerHighest = LightCard,
    surfaceTint = Color.Transparent,
    outline = LightOutline,
    outlineVariant = LightOutline,
    error = Color(0xFFDC2626),
    onError = Color.White,
)

private fun darkScheme(p: Palette): ColorScheme {
    val bright = p.primary.lighten(0.30f)
    return darkColorScheme(
        primary = bright,
        onPrimary = Color(0xFF0E1F17),
        primaryContainer = p.primary,
        onPrimaryContainer = Color.White,
        secondary = bright,
        onSecondary = Color(0xFF0E1F17),
        secondaryContainer = p.primary,
        onSecondaryContainer = Color.White,
        tertiary = p.accent.lighten(0.25f),
        onTertiary = Color(0xFF1A1A1A),
        background = DarkBackground,
        onBackground = DarkOnSurface,
        surface = DarkCard,
        onSurface = DarkOnSurface,
        surfaceVariant = DarkVariant,
        onSurfaceVariant = DarkOnVariant,
        surfaceContainerLowest = DarkBackground,
        surfaceContainerLow = DarkCard,
        surfaceContainer = DarkCard,
        surfaceContainerHigh = DarkCard,
        surfaceContainerHighest = DarkCard,
        surfaceTint = Color.Transparent,
        outline = DarkOutline,
        outlineVariant = DarkOutline,
        error = Color(0xFFF87171),
        onError = Color(0xFF1A1A1A),
    )
}

private fun Color.compositeOverWhite(): Color {
    val a = alpha
    return Color(
        red = red * a + (1 - a),
        green = green * a + (1 - a),
        blue = blue * a + (1 - a),
    )
}

private fun Color.lighten(t: Float) = Color(
    red = red + (1 - red) * t,
    green = green + (1 - green) * t,
    blue = blue + (1 - blue) * t,
)

@Composable
fun AskesisTheme(
    schemeName: String = "forest",
    themeMode: String = "system",
    content: @Composable () -> Unit,
) {
    val palette = schemes[schemeName] ?: schemes.getValue("forest")
    val dark = when (themeMode) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    MaterialTheme(
        colorScheme = if (dark) darkScheme(palette) else lightScheme(palette),
        typography = AskesisTypography,
        content = content,
    )
}
