package app.askesis.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.askesis.ui.theme.Accent

/** A rounded, tinted icon badge — the colored square the web app puts on metric/section headers. */
@Composable
fun IconBadge(icon: ImageVector, color: Color, size: Int = 36) {
    Box(
        modifier = Modifier
            .size(size.dp)
            .background(color.copy(alpha = 0.15f), RoundedCornerShape(10.dp)),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size((size * 0.55f).dp))
    }
}

/**
 * A dashboard metric card: big bold value + small unit, with a tinted icon badge on the right —
 * the web's MetricSnapshotCard look.
 */
@Composable
fun MetricStat(
    label: String,
    value: String,
    unit: String?,
    icon: ImageVector,
    color: Color,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    AppCard(modifier = if (onClick != null) modifier.clickable(onClick = onClick) else modifier) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        value,
                        style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
                    )
                    if (unit != null) {
                        Text(
                            " $unit",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(bottom = 3.dp),
                        )
                    }
                }
            }
            IconBadge(icon, color)
        }
    }
}

/** A card/section title preceded by a tinted icon — the web header style ("🔥 Today's Nutrition"). */
@Composable
fun SectionHeader(icon: ImageVector, title: String, color: Color, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(20.dp))
        Text(title, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold))
    }
}

/** Field label row: colored icon + bold label + faint unit hint, shown above the input. */
@Composable
fun FieldLabel(icon: ImageVector, label: String, hint: String?, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(16.dp))
        Text(label, style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold))
        if (hint != null) {
            Text(hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private val FieldShape = RoundedCornerShape(12.dp)

/** Numeric field with an icon+label header above a clean, label-less input (web `.input` look). */
@Composable
fun LabeledNumberField(
    icon: ImageVector,
    label: String,
    hint: String?,
    color: Color,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    decimal: Boolean = true,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FieldLabel(icon, label, hint, color)
        OutlinedTextField(
            value = value,
            onValueChange = { new ->
                if (new.isEmpty() || new.matches(if (decimal) Regex("^\\d*\\.?\\d*$") else Regex("^\\d*$"))) {
                    onValueChange(new)
                }
            },
            singleLine = true,
            shape = FieldShape,
            keyboardOptions = KeyboardOptions(keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = MaterialTheme.colorScheme.primary,
                unfocusedBorderColor = MaterialTheme.colorScheme.outline,
            ),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/** Text field with an icon+label header (used for Notes etc). */
@Composable
fun LabeledTextField(
    icon: ImageVector,
    label: String,
    color: Color,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    singleLine: Boolean = true,
    minLines: Int = 1,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FieldLabel(icon, label, null, color)
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = singleLine,
            minLines = minLines,
            shape = FieldShape,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = MaterialTheme.colorScheme.primary,
                unfocusedBorderColor = MaterialTheme.colorScheme.outline,
            ),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/** A small rounded type/category pill (cardio=blue, strength=purple) — the web activity badge. */
@Composable
fun TypePill(text: String, color: Color) {
    Box(
        Modifier
            .background(color.copy(alpha = 0.15f), RoundedCornerShape(50))
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelMedium, color = color, fontWeight = FontWeight.Medium)
    }
}

/** Pick the activity-type accent color (cardio=blue, strength=purple). */
fun activityColor(type: String): Color = if (type == "strength") Accent.Strength else Accent.Cardio

// ── Feelings (emoji + color), matching the web FEELINGS list ──
data class Feeling(val value: String, val emoji: String, val label: String, val color: Color)

val FEELINGS = listOf(
    Feeling("happy", "😊", "Happy", Accent.Mood5),
    Feeling("energetic", "⚡", "Energetic", Accent.Cardio),
    Feeling("calm", "😌", "Calm", Accent.Rest),
    Feeling("focused", "🎯", "Focused", Color(0xFF3D8B65)),
    Feeling("grateful", "🙏", "Grateful", Accent.Mood4),
    Feeling("motivated", "💪", "Motivated", Accent.Strength),
    Feeling("tired", "😴", "Tired", Accent.Mood2),
    Feeling("stressed", "😰", "Stressed", Accent.Mood1),
    Feeling("anxious", "😟", "Anxious", Accent.Nutrition600),
    Feeling("sad", "😢", "Sad", Accent.Mood1),
    Feeling("angry", "😤", "Angry", Color(0xFFF76A4D)),
    Feeling("sick", "🤒", "Sick", Accent.Mood2),
    Feeling("sore", "🤕", "Sore", Accent.Mood3),
    Feeling("meh", "😐", "Meh", Color(0xFF6B7280)),
)

/** Multi-select feeling chips: emoji + label, filled with the feeling's color when selected. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FeelingFlow(selected: Set<String>, onToggle: (String) -> Unit, modifier: Modifier = Modifier) {
    FlowRow(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FEELINGS.forEach { f ->
            val on = f.value in selected
            Row(
                modifier = Modifier
                    .background(
                        if (on) f.color else MaterialTheme.colorScheme.surfaceVariant,
                        RoundedCornerShape(50),
                    )
                    .then(
                        if (on) Modifier
                        else Modifier.border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(50)),
                    )
                    .clickable { onToggle(f.value) }
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(f.emoji)
                Text(
                    f.label,
                    style = MaterialTheme.typography.labelLarge,
                    color = if (on) Color.White else MaterialTheme.colorScheme.onSurface,
                    fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                )
            }
        }
    }
}
