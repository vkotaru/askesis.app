package app.askesis.ui.components

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * The "Askesis" wordmark — bold, with the same left-to-right brand gradient the web app
 * paints across its header (`bg-gradient-to-r from-primary-600 to-primary-400`). Shown in
 * the top app bar so the native app leads with the brand exactly like the website does.
 */
@Composable
fun BrandWordmark(modifier: Modifier = Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    val lighter = Color(
        red = primary.red + (1 - primary.red) * 0.35f,
        green = primary.green + (1 - primary.green) * 0.35f,
        blue = primary.blue + (1 - primary.blue) * 0.35f,
    )
    Text(
        text = "Askesis",
        modifier = modifier,
        style = MaterialTheme.typography.titleLarge.copy(
            fontWeight = FontWeight.Bold,
            brush = Brush.linearGradient(listOf(primary, lighter)),
        ),
    )
}

/**
 * The app's standard card: a white (surface) panel with rounded corners and the soft
 * shadow the web app uses (`.card` → `shadow-soft`). Used everywhere instead of the
 * default tonal [androidx.compose.material3.Card] so the UI matches the website.
 */
@Composable
fun AppCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    ElevatedCard(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.elevatedCardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.elevatedCardElevation(defaultElevation = 3.dp),
        content = content,
    )
}

val ISO: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd")

fun today(): String = LocalDate.now().format(ISO)

fun prettyDate(iso: String): String = try {
    LocalDate.parse(iso, ISO).format(DateTimeFormatter.ofPattern("EEE, MMM d"))
} catch (_: Exception) {
    iso
}

/** Shift an ISO date by [n] days (negative = earlier). */
fun addDays(iso: String, n: Long): String = LocalDate.parse(iso, ISO).plusDays(n).format(ISO)

/**
 * Convert ISO date <-> epoch millis using UTC, the convention Material3's DatePicker uses for
 * `initialSelectedDateMillis`. Going through UTC (not the default zone) avoids the off-by-one-day
 * drift that bites date pickers in non-UTC timezones.
 */
fun isoToEpochMillis(iso: String): Long =
    LocalDate.parse(iso, ISO).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()

fun epochMillisToIso(millis: Long): String =
    Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate().format(ISO)

/** A numeric text field bound to a String state. Empty string means "unset". */
@Composable
fun NumberField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier.fillMaxWidth(),
    decimal: Boolean = true,
    suffix: String? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { new ->
            if (new.isEmpty() || new.matches(if (decimal) Regex("^\\d*\\.?\\d*$") else Regex("^\\d*$"))) {
                onValueChange(new)
            }
        },
        label = { Text(label) },
        singleLine = true,
        suffix = suffix?.let { { Text(it) } },
        keyboardOptions = KeyboardOptions(
            keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number
        ),
        modifier = modifier,
    )
}

@Composable
fun PlainField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier.fillMaxWidth(),
    singleLine: Boolean = true,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = singleLine,
        modifier = modifier,
    )
}

/** Parse helpers tolerating blank input. */
fun String.toDoubleOrNullSafe(): Double? = trim().takeIf { it.isNotEmpty() }?.toDoubleOrNull()
fun String.toIntOrNullSafe(): Int? = trim().takeIf { it.isNotEmpty() }?.toDoubleOrNull()?.toInt()
fun Double?.orBlank(): String = this?.let { if (it == it.toLong().toDouble()) it.toLong().toString() else it.toString() } ?: ""
fun Int?.orBlank(): String = this?.toString() ?: ""
