package app.askesis.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import app.askesis.R

/**
 * Space Grotesk — the same typeface the web app uses (`--font-sans`). Loaded from the
 * bundled variable TTF; each weight maps onto the font's `wght` axis via Compose's
 * default variation settings.
 */
val SpaceGrotesk = FontFamily(
    Font(R.font.space_grotesk, FontWeight.Light),
    Font(R.font.space_grotesk, FontWeight.Normal),
    Font(R.font.space_grotesk, FontWeight.Medium),
    Font(R.font.space_grotesk, FontWeight.SemiBold),
    Font(R.font.space_grotesk, FontWeight.Bold),
)

/** Material 3 type scale with every role re-pointed at Space Grotesk. */
val AskesisTypography: Typography = Typography().run {
    Typography(
        displayLarge = displayLarge.copy(fontFamily = SpaceGrotesk),
        displayMedium = displayMedium.copy(fontFamily = SpaceGrotesk),
        displaySmall = displaySmall.copy(fontFamily = SpaceGrotesk),
        headlineLarge = headlineLarge.copy(fontFamily = SpaceGrotesk),
        headlineMedium = headlineMedium.copy(fontFamily = SpaceGrotesk),
        headlineSmall = headlineSmall.copy(fontFamily = SpaceGrotesk),
        titleLarge = titleLarge.copy(fontFamily = SpaceGrotesk),
        titleMedium = titleMedium.copy(fontFamily = SpaceGrotesk),
        titleSmall = titleSmall.copy(fontFamily = SpaceGrotesk),
        bodyLarge = bodyLarge.copy(fontFamily = SpaceGrotesk),
        bodyMedium = bodyMedium.copy(fontFamily = SpaceGrotesk),
        bodySmall = bodySmall.copy(fontFamily = SpaceGrotesk),
        labelLarge = labelLarge.copy(fontFamily = SpaceGrotesk),
        labelMedium = labelMedium.copy(fontFamily = SpaceGrotesk),
        labelSmall = labelSmall.copy(fontFamily = SpaceGrotesk),
    )
}
