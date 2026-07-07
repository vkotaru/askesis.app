package app.askesis.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.repo.AskesisRepository
import app.askesis.ui.components.AppCard
import app.askesis.ui.components.DateNavBar
import app.askesis.ui.components.NumberField
import app.askesis.ui.components.RecentList
import app.askesis.ui.components.SectionHeader
import app.askesis.ui.components.toDoubleOrNullSafe
import app.askesis.ui.components.today
import app.askesis.ui.repository
import app.askesis.ui.theme.Accent
import app.askesis.ui.util.editValue
import app.askesis.ui.util.formatMeasurement
import app.askesis.ui.util.measurementFromMetric
import app.askesis.ui.util.measurementLabel
import app.askesis.ui.util.measurementToMetric
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

private val FIELDS = listOf(
    "neck" to "Neck", "shoulders" to "Shoulders", "chest" to "Chest",
    "bicepLeft" to "Bicep L", "bicepRight" to "Bicep R",
    "forearmLeft" to "Forearm L", "forearmRight" to "Forearm R",
    "waist" to "Waist", "abdomen" to "Abdomen", "hips" to "Hips",
    "thighLeft" to "Thigh L", "thighRight" to "Thigh R",
    "calfLeft" to "Calf L", "calfRight" to "Calf R",
)

class MeasurementsViewModel(private val repo: AskesisRepository) : ViewModel() {
    var date by mutableStateOf(today()); private set
    val values = mutableStateMapOf<String, String>()
    var notes by mutableStateOf("")
    var saved by mutableStateOf(false)
    var unit by mutableStateOf("cm"); private set

    val recent = repo.observeRecentMeasurements(10)

    init {
        load()
        repo.settings.settings.onEach { s ->
            val changed = unit != s.measurementUnit
            unit = s.measurementUnit
            if (changed) load()
        }.launchIn(viewModelScope)
    }

    fun changeDate(d: String) { date = d; load() }

    private fun load() = viewModelScope.launch {
        val m = repo.measurement(date)
        fun g(d: Double?) = editValue(d?.let { measurementFromMetric(it, unit) })
        values["neck"] = g(m?.neck); values["shoulders"] = g(m?.shoulders); values["chest"] = g(m?.chest)
        values["bicepLeft"] = g(m?.bicepLeft); values["bicepRight"] = g(m?.bicepRight)
        values["forearmLeft"] = g(m?.forearmLeft); values["forearmRight"] = g(m?.forearmRight)
        values["waist"] = g(m?.waist); values["abdomen"] = g(m?.abdomen); values["hips"] = g(m?.hips)
        values["thighLeft"] = g(m?.thighLeft); values["thighRight"] = g(m?.thighRight)
        values["calfLeft"] = g(m?.calfLeft); values["calfRight"] = g(m?.calfRight)
        notes = m?.notes ?: ""
        saved = false
    }

    fun save() = viewModelScope.launch {
        fun v(k: String) = values[k].orEmpty().toDoubleOrNullSafe()?.let { measurementToMetric(it, unit) }
        repo.saveMeasurement(
            MeasurementEntity(
                uid = "", date = date,
                neck = v("neck"), shoulders = v("shoulders"), chest = v("chest"),
                bicepLeft = v("bicepLeft"), bicepRight = v("bicepRight"),
                forearmLeft = v("forearmLeft"), forearmRight = v("forearmRight"),
                waist = v("waist"), abdomen = v("abdomen"), hips = v("hips"),
                thighLeft = v("thighLeft"), thighRight = v("thighRight"),
                calfLeft = v("calfLeft"), calfRight = v("calfRight"),
                notes = notes.ifBlank { null },
            )
        )
        saved = true
    }

    companion object {
        val Factory = viewModelFactory { initializer { MeasurementsViewModel(repository()) } }
    }
}

@Composable
fun MeasurementsScreen(vm: MeasurementsViewModel = viewModel(factory = MeasurementsViewModel.Factory)) {
    val recent by vm.recent.collectAsState(initial = emptyList())

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        DateNavBar(vm.date, { vm.changeDate(it) }, hasData = recent.any { it.date == vm.date })

        AppCard(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                SectionHeader(Icons.Filled.Straighten, "Body measurements", Accent.Rest)
                Text(
                    "All values in ${measurementLabel(vm.unit)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                FIELDS.chunked(2).forEach { pair ->
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                        pair.forEach { (key, label) ->
                            NumberField(
                                label = label,
                                value = vm.values[key].orEmpty(),
                                onValueChange = { vm.values[key] = it },
                                modifier = Modifier.weight(1f),
                                suffix = measurementLabel(vm.unit),
                            )
                        }
                        if (pair.size == 1) Spacer1()
                    }
                }

                app.askesis.ui.components.PlainField("Notes", vm.notes, { vm.notes = it }, singleLine = false)

                Row(Modifier.fillMaxWidth(), horizontalArrangement = androidx.compose.foundation.layout.Arrangement.End) {
                    Button(onClick = { vm.save() }) {
                        Text(if (vm.saved) "Saved ✓" else "Save")
                    }
                }
            }
        }

        RecentList(
            title = "Recent entries",
            items = recent,
            selectedDate = vm.date,
            dateOf = { it.date },
            summary = { m ->
                listOfNotNull(
                    m.chest?.let { "Chest ${formatMeasurement(it, vm.unit)}" },
                    m.waist?.let { "Waist ${formatMeasurement(it, vm.unit)}" },
                    m.hips?.let { "Hips ${formatMeasurement(it, vm.unit)}" },
                ).joinToString(" · ").ifBlank { null }
            },
            onSelect = { vm.changeDate(it) },
        )
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.Spacer1() {
    androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
}
