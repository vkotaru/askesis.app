package app.askesis.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Notes
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.LocalCafe
import androidx.compose.material.icons.filled.MonitorWeight
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.toMutableStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import app.askesis.data.local.entity.DailyLogEntity
import app.askesis.data.repo.AskesisRepository
import app.askesis.ui.components.AppCard
import app.askesis.ui.components.DateNavBar
import app.askesis.ui.components.FeelingFlow
import app.askesis.ui.components.FieldLabel
import app.askesis.ui.components.LabeledNumberField
import app.askesis.ui.components.LabeledTextField
import app.askesis.ui.components.RecentList
import app.askesis.ui.components.orBlank
import app.askesis.ui.components.toDoubleOrNullSafe
import app.askesis.ui.components.toIntOrNullSafe
import app.askesis.ui.components.today
import app.askesis.ui.repository
import app.askesis.ui.theme.Accent
import app.askesis.ui.util.editValue
import app.askesis.ui.util.formatWater
import app.askesis.ui.util.formatWeight
import app.askesis.ui.util.waterFromMetric
import app.askesis.ui.util.waterLabel
import app.askesis.ui.util.waterToMetric
import app.askesis.ui.util.weightFromMetric
import app.askesis.ui.util.weightLabel
import app.askesis.ui.util.weightToMetric
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

class DailyLogViewModel(private val repo: AskesisRepository) : ViewModel() {
    var date by mutableStateOf(today()); private set
    var weight by mutableStateOf("")
    var sleep by mutableStateOf("")
    var steps by mutableStateOf("")
    var water by mutableStateOf("")
    var caffeine by mutableStateOf("")
    val feelings = mutableListOf<String>().toMutableStateList()
    var notes by mutableStateOf("")
    var ateOutside by mutableStateOf(false)
    var saved by mutableStateOf(false)

    var weightUnit by mutableStateOf("kg"); private set
    var waterUnit by mutableStateOf("ml"); private set

    val recent = repo.observeRecentLogs(10)

    init {
        load()
        repo.settings.settings.onEach { s ->
            val changed = weightUnit != s.weightUnit || waterUnit != s.waterUnit
            weightUnit = s.weightUnit
            waterUnit = s.waterUnit
            if (changed) load()
        }.launchIn(viewModelScope)
    }

    fun changeDate(d: String) { date = d; load() }

    fun toggleFeeling(v: String) {
        if (!feelings.remove(v)) feelings.add(v)
        saved = false
    }

    private fun load() = viewModelScope.launch {
        val l = repo.dailyLog(date)
        weight = editValue(l?.weight?.let { weightFromMetric(it, weightUnit) })
        sleep = l?.sleepHours.orBlank()
        steps = l?.steps.orBlank()
        water = editValue(l?.waterMl?.let { waterFromMetric(it, waterUnit) })
        caffeine = l?.caffeineMg.orBlank()
        feelings.clear()
        l?.feelings?.split(",")?.map { it.trim() }?.filter { it.isNotEmpty() }?.let { feelings.addAll(it) }
        notes = l?.notes ?: ""
        ateOutside = l?.ateOutside ?: false
        saved = false
    }

    fun save() = viewModelScope.launch {
        repo.saveDailyLog(
            DailyLogEntity(
                uid = "", date = date,
                weight = weight.toDoubleOrNullSafe()?.let { weightToMetric(it, weightUnit) },
                sleepHours = sleep.toDoubleOrNullSafe(),
                steps = steps.toIntOrNullSafe(),
                waterMl = water.toDoubleOrNullSafe()?.let { waterToMetric(it, waterUnit) },
                caffeineMg = caffeine.toIntOrNullSafe(),
                feelings = feelings.joinToString(",").ifBlank { null },
                notes = notes.ifBlank { null },
                ateOutside = ateOutside,
            )
        )
        saved = true
    }

    companion object {
        val Factory = viewModelFactory { initializer { DailyLogViewModel(repository()) } }
    }
}

@Composable
fun DailyLogScreen(vm: DailyLogViewModel = viewModel(factory = DailyLogViewModel.Factory)) {
    val recent by vm.recent.collectAsState(initial = emptyList())
    val hasData = recent.any { it.date == vm.date }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        DateNavBar(vm.date, { vm.changeDate(it) }, hasData = hasData)
        if (hasData) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.height(16.dp))
                Text("Data recorded", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
            }
        }

        AppCard(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    LabeledNumberField(Icons.Filled.MonitorWeight, "Weight", "(${weightLabel(vm.weightUnit)})", Accent.Rest, vm.weight, { vm.weight = it }, Modifier.weight(1f))
                    LabeledNumberField(Icons.Filled.Bedtime, "Sleep", "(hrs)", Accent.Strength, vm.sleep, { vm.sleep = it }, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    LabeledNumberField(Icons.Filled.DirectionsWalk, "Steps", null, Accent.Cardio, vm.steps, { vm.steps = it }, Modifier.weight(1f), decimal = false)
                    LabeledNumberField(Icons.Filled.WaterDrop, "Water", "(${waterLabel(vm.waterUnit)})", Accent.Cardio, vm.water, { vm.water = it }, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
                    LabeledNumberField(Icons.Filled.LocalCafe, "Caffeine", "(mg)", Accent.Nutrition600, vm.caffeine, { vm.caffeine = it }, Modifier.weight(1f), decimal = false)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        FieldLabel(Icons.Filled.Restaurant, "Ate outside", null, Accent.Nutrition)
                        Switch(
                            checked = vm.ateOutside,
                            onCheckedChange = { vm.ateOutside = it },
                            colors = SwitchDefaults.colors(checkedTrackColor = Accent.Nutrition),
                        )
                    }
                }

                FieldLabel(Icons.Filled.Favorite, "How are you feeling?", "(select all that apply)", Color(0xFFF76A4D))
                FeelingFlow(vm.feelings.toSet(), { vm.toggleFeeling(it) })

                LabeledTextField(Icons.AutoMirrored.Filled.Notes, "Notes", MaterialTheme.colorScheme.onSurfaceVariant, vm.notes, { vm.notes = it }, singleLine = false, minLines = 3)

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    Button(onClick = { vm.save() }) {
                        Text(if (vm.saved) "Saved ✓" else "Save Log")
                    }
                }
            }
        }

        RecentList(
            title = "Recent entries",
            items = recent,
            selectedDate = vm.date,
            dateOf = { it.date },
            summary = { l ->
                listOfNotNull(
                    l.weight?.let { formatWeight(it, vm.weightUnit) },
                    l.steps?.let { "$it steps" },
                    l.sleepHours?.let { "${it}h" },
                    l.waterMl?.let { formatWater(it, vm.waterUnit) },
                ).joinToString(" · ").ifBlank { null }
            },
            onSelect = { vm.changeDate(it) },
        )

        Spacer(Modifier.height(4.dp))
    }
}
