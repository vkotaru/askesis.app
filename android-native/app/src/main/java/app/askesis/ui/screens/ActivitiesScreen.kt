package app.askesis.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material3.AlertDialog
import app.askesis.ui.components.AppCard as Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.compose.runtime.collectAsState
import app.askesis.data.local.entity.ActivityEntity
import app.askesis.data.model.ExerciseSet
import app.askesis.data.model.Structured
import app.askesis.data.repo.AskesisRepository
import app.askesis.ui.components.DateNavBar
import app.askesis.ui.components.IconBadge
import app.askesis.ui.components.NumberField
import app.askesis.ui.components.PlainField
import app.askesis.ui.components.RecentList
import app.askesis.ui.components.TypePill
import app.askesis.ui.components.activityColor
import app.askesis.ui.components.toDoubleOrNullSafe
import app.askesis.ui.components.toIntOrNullSafe
import app.askesis.ui.components.today
import app.askesis.ui.repository
import app.askesis.ui.util.distanceFromMetric
import app.askesis.ui.util.distanceLabel
import app.askesis.ui.util.distanceToMetric
import app.askesis.ui.util.editValue
import app.askesis.ui.util.formatDistance
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

class ActivitiesViewModel(private val repo: AskesisRepository) : ViewModel() {
    var date by mutableStateOf(today()); private set
    var distanceUnit by mutableStateOf("km"); private set

    /** Activities logged on the selected day (the main list). */
    fun activitiesFor(d: String) = repo.observeActivitiesForDate(d)

    /** Recent activities across all days (history list — tap to jump to that date). */
    val recent = repo.observeRecentActivities(20)

    init {
        repo.settings.settings.onEach { distanceUnit = it.distanceUnit }.launchIn(viewModelScope)
    }

    fun changeDate(d: String) { date = d }

    fun upsert(
        uid: String, name: String, type: String, duration: String, calories: String,
        distance: String, notes: String, exercises: List<ExerciseSet>,
    ) = viewModelScope.launch {
        repo.saveActivity(
            ActivityEntity(
                uid = uid, date = date, name = name, activityType = type,
                durationMins = duration.toIntOrNullSafe(),
                calories = calories.toIntOrNullSafe(),
                distanceKm = distance.toDoubleOrNullSafe()?.let { distanceToMetric(it, distanceUnit) },
                notes = notes.ifBlank { null },
                exercisesJson = Structured.encodeExercises(exercises),
            )
        )
    }

    fun delete(uid: String) = viewModelScope.launch { repo.deleteActivity(uid) }

    companion object {
        val Factory = viewModelFactory { initializer { ActivitiesViewModel(repository()) } }
    }
}

@Composable
fun ActivitiesScreen(vm: ActivitiesViewModel = viewModel(factory = ActivitiesViewModel.Factory)) {
    val list by remember(vm.date) { vm.activitiesFor(vm.date) }.collectAsState(initial = emptyList())
    val recent by vm.recent.collectAsState(initial = emptyList())
    var showAdd by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<ActivityEntity?>(null) }

    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DateNavBar(vm.date, { vm.changeDate(it) }, hasData = list.isNotEmpty())

            if (list.isEmpty()) {
                Text(
                    "No activities on this day. Tap + to log a workout.",
                    modifier = Modifier.padding(vertical = 24.dp),
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                list.forEach { a ->
                    val accent = activityColor(a.activityType)
                    Card(Modifier.fillMaxWidth()) {
                        Row(
                            Modifier.fillMaxWidth().padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            IconBadge(if (a.activityType == "strength") Icons.Filled.FitnessCenter else Icons.Filled.DirectionsRun, accent)
                            Column(Modifier.weight(1f)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(a.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f, fill = false))
                                    TypePill(a.activityType, accent)
                                }
                                val parts = buildList {
                                    a.durationMins?.let { add("$it min") }
                                    a.distanceKm?.let { add(formatDistance(it, vm.distanceUnit)) }
                                    a.calories?.let { add("$it kcal") }
                                }
                                if (parts.isNotEmpty()) Text(parts.joinToString(" · "), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                val exercises = Structured.decodeExercises(a.exercisesJson)
                                if (exercises.isNotEmpty()) {
                                    Text(
                                        exercises.joinToString(", ") { e ->
                                            e.name + listOfNotNull(
                                                e.sets?.let { s -> e.reps?.let { r -> "${s}×$r" } },
                                                e.weight?.let { "@${it}kg" },
                                            ).joinToString(" ").let { if (it.isBlank()) "" else " $it" }
                                        },
                                        style = MaterialTheme.typography.bodySmall,
                                    )
                                }
                            }
                            IconButton(onClick = { editing = a }) {
                                Icon(Icons.Filled.Edit, contentDescription = "Edit")
                            }
                            IconButton(onClick = { vm.delete(a.uid) }) {
                                Icon(Icons.Filled.Delete, contentDescription = "Delete")
                            }
                        }
                    }
                }
            }

            RecentList(
                title = "Recent workouts",
                items = recent,
                selectedDate = vm.date,
                dateOf = { it.date },
                summary = { a ->
                    a.name + (a.durationMins?.let { " · $it min" } ?: "") +
                        (a.distanceKm?.let { " · ${formatDistance(it, vm.distanceUnit)}" } ?: "")
                },
                onSelect = { vm.changeDate(it) },
            )
        }

        FloatingActionButton(
            onClick = { showAdd = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        ) { Icon(Icons.Filled.Add, contentDescription = "Add activity") }
    }

    if (showAdd || editing != null) {
        val current = editing
        key(current?.uid) {
            ActivityDialog(
                initial = current,
                unit = vm.distanceUnit,
                onDismiss = { showAdd = false; editing = null },
                onSave = { uid, name, type, dur, cal, dist, notes, exercises ->
                    vm.upsert(uid, name, type, dur, cal, dist, notes, exercises)
                    showAdd = false; editing = null
                },
            )
        }
    }
}

@Composable
private fun ActivityDialog(
    initial: ActivityEntity?,
    unit: String,
    onDismiss: () -> Unit,
    onSave: (String, String, String, String, String, String, String, List<ExerciseSet>) -> Unit,
) {
    var name by remember { mutableStateOf(initial?.name ?: "") }
    var type by remember { mutableStateOf(initial?.activityType ?: "cardio") }
    var duration by remember { mutableStateOf(initial?.durationMins?.toString() ?: "") }
    var calories by remember { mutableStateOf(initial?.calories?.toString() ?: "") }
    var distance by remember { mutableStateOf(editValue(initial?.distanceKm?.let { distanceFromMetric(it, unit) })) }
    var notes by remember { mutableStateOf(initial?.notes ?: "") }
    val exercises = remember { mutableStateListOf<ExerciseSet>().apply { addAll(Structured.decodeExercises(initial?.exercisesJson)) } }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (initial == null) "Log activity" else "Edit activity") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                PlainField("Name", name, { name = it })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("cardio", "strength").forEach { t ->
                        FilterChip(selected = type == t, onClick = { type = t }, label = { Text(t) })
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumberField("Min", duration, { duration = it }, Modifier.weight(1f), decimal = false)
                    NumberField("kcal", calories, { calories = it }, Modifier.weight(1f), decimal = false)
                }
                if (type == "strength") {
                    ExercisesEditor(exercises)
                } else {
                    NumberField("Distance", distance, { distance = it }, suffix = distanceLabel(unit))
                }
                PlainField("Notes", notes, { notes = it }, singleLine = false)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(
                        initial?.uid ?: "", name, type, duration, calories, distance, notes,
                        if (type == "strength") exercises.toList() else emptyList(),
                    )
                },
                enabled = name.isNotBlank(),
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun ExercisesEditor(exercises: SnapshotStateList<ExerciseSet>) {
    var name by remember { mutableStateOf("") }
    var sets by remember { mutableStateOf("") }
    var reps by remember { mutableStateOf("") }
    var weight by remember { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Exercises", style = MaterialTheme.typography.labelLarge)
        exercises.forEachIndexed { i, e ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    e.name + listOfNotNull(
                        e.sets?.let { s -> e.reps?.let { r -> " ${s}×$r" } },
                        e.weight?.let { " @${it}kg" },
                    ).joinToString(""),
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.bodyMedium,
                )
                IconButton(onClick = { exercises.removeAt(i) }) {
                    Icon(Icons.Filled.Delete, contentDescription = "Remove exercise")
                }
            }
        }
        PlainField("Exercise", name, { name = it })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            NumberField("Sets", sets, { sets = it }, Modifier.weight(1f), decimal = false)
            NumberField("Reps", reps, { reps = it }, Modifier.weight(1f), decimal = false)
            NumberField("kg", weight, { weight = it }, Modifier.weight(1f))
        }
        TextButton(
            onClick = {
                exercises.add(
                    ExerciseSet(name.trim(), sets.toIntOrNullSafe(), reps.toIntOrNullSafe(), weight.toDoubleOrNullSafe())
                )
                name = ""; sets = ""; reps = ""; weight = ""
            },
            enabled = name.isNotBlank(),
        ) { Text("Add exercise") }
    }
}
