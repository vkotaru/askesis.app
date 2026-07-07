package app.askesis.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * The `[‹]  date pill  [›]` control the web app shows on every data-entry page. Tapping the pill
 * opens a Material date picker; the chevrons step a day at a time. [hasData] tints the pill so the
 * user can see at a glance whether the selected day already has an entry (matches the web's
 * "Data recorded" affordance).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateNavBar(
    date: String,
    onDateChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    hasData: Boolean = false,
) {
    var showPicker by remember { mutableStateOf(false) }

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = { onDateChange(addDays(date, -1)) }) {
            Icon(Icons.Filled.ChevronLeft, contentDescription = "Previous day")
        }
        Surface(
            onClick = { showPicker = true },
            shape = RoundedCornerShape(12.dp),
            color = if (hasData) MaterialTheme.colorScheme.primaryContainer
            else MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.weight(1f),
        ) {
            Text(
                prettyDate(date),
                modifier = Modifier.padding(vertical = 10.dp),
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                color = if (hasData) MaterialTheme.colorScheme.onPrimaryContainer
                else MaterialTheme.colorScheme.onSurface,
            )
        }
        IconButton(onClick = { onDateChange(addDays(date, 1)) }) {
            Icon(Icons.Filled.ChevronRight, contentDescription = "Next day")
        }
    }

    if (showPicker) {
        val state = rememberDatePickerState(initialSelectedDateMillis = isoToEpochMillis(date))
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { onDateChange(epochMillisToIso(it)) }
                    showPicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showPicker = false }) { Text("Cancel") } },
        ) {
            DatePicker(state = state)
        }
    }
}

/**
 * A compact "recent entries" card: each row shows its date (bold + highlighted when it's the
 * currently selected day) plus a one-line [summary]; tapping a row jumps the screen to that date
 * (mirrors the web recent-entries tables).
 */
@Composable
fun <T> RecentList(
    title: String,
    items: List<T>,
    selectedDate: String,
    dateOf: (T) -> String,
    summary: (T) -> String?,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (items.isEmpty()) return
    AppCard(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 4.dp))
            items.forEach { item ->
                val d = dateOf(item)
                val active = d == selectedDate
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clickable { onSelect(d) }
                        .padding(vertical = 8.dp),
                ) {
                    Text(
                        prettyDate(d),
                        style = MaterialTheme.typography.bodyMedium.copy(
                            fontWeight = if (active) FontWeight.Bold else FontWeight.Medium,
                        ),
                        color = if (active) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurface,
                    )
                    summary(item)?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}
