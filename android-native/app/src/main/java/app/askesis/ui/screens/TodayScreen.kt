package app.askesis.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import app.askesis.ui.components.AppCard as Card
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.LocalCafe
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.MonitorWeight
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import coil.compose.AsyncImage
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.local.entity.PhotoEntity
import app.askesis.data.prefs.SettingsStore
import app.askesis.data.repo.AskesisRepository
import app.askesis.data.sync.SyncController
import app.askesis.ui.components.BarChart
import app.askesis.ui.components.LineChart
import app.askesis.ui.components.MetricStat
import app.askesis.ui.components.SectionHeader
import app.askesis.ui.components.TargetProgressBar
import app.askesis.ui.components.TypePill
import app.askesis.ui.components.activityColor
import app.askesis.ui.components.prettyDate
import app.askesis.ui.components.today
import app.askesis.ui.nav.Dest
import app.askesis.ui.repository
import app.askesis.ui.theme.Accent
import app.askesis.ui.util.formatMeasurement
import app.askesis.ui.util.formatWater
import app.askesis.ui.util.formatWeight
import app.askesis.ui.util.weightFromMetric
import app.askesis.ui.util.weightLabel
import kotlinx.coroutines.launch
import java.io.File

class TodayViewModel(private val repo: AskesisRepository) : ViewModel() {
    val log = repo.observeDailyLog(today())
    val meals = repo.observeMealsForDate(today())
    val activities = repo.observeRecentActivities(5)
    val recentLogs = repo.observeRecentLogs(30)
    val settings = repo.settings.settings
    val syncState = repo.syncState
    suspend fun latestMeasurement(): MeasurementEntity? = repo.latestMeasurement()
    suspend fun latestPhoto(): PhotoEntity? = repo.latestPhoto()
    fun syncNow() = viewModelScope.launch { repo.runSync() }

    companion object {
        val Factory = viewModelFactory { initializer { TodayViewModel(repository()) } }
    }
}

private fun movingAvg(v: List<Float>, window: Int = 7): List<Float> =
    v.indices.map { i -> v.subList(maxOf(0, i - window + 1), i + 1).average().toFloat() }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(
    onNavigate: (String) -> Unit,
    vm: TodayViewModel = viewModel(factory = TodayViewModel.Factory),
) {
    val log by vm.log.collectAsState(initial = null)
    val meals by vm.meals.collectAsState(initial = emptyList())
    val activities by vm.activities.collectAsState(initial = emptyList())
    val recentLogs by vm.recentLogs.collectAsState(initial = emptyList())
    val s by vm.settings.collectAsState(initial = SettingsStore.Settings())
    val syncState by vm.syncState.collectAsState()
    var latest by remember { mutableStateOf<MeasurementEntity?>(null) }
    var photo by remember { mutableStateOf<PhotoEntity?>(null) }
    LaunchedEffect(Unit) { latest = vm.latestMeasurement() }
    LaunchedEffect(syncState) { photo = vm.latestPhoto() }

    PullToRefreshBox(
        isRefreshing = syncState is SyncController.State.Syncing,
        onRefresh = { vm.syncNow() },
        modifier = Modifier.fillMaxSize(),
    ) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(prettyDate(today()), style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold))

            val totalCalories = meals.sumOf { it.calories ?: 0 }
            val caloriesValue = when {
                s.calorieTarget > 0 -> "$totalCalories / ${s.calorieTarget}"
                totalCalories > 0 -> "$totalCalories"
                else -> "—"
            }
            // Metric snapshot cards with tinted icon badges (matches web MetricSnapshotCard).
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricStat("Weight", formatWeightValue(log?.weight, s.weightUnit), weightUnitOrNull(log?.weight, s.weightUnit), Icons.Filled.MonitorWeight, Accent.Rest, Modifier.weight(1f)) { onNavigate(Dest.Daily.route) }
                MetricStat("Calories", caloriesValue, null, Icons.Filled.LocalFireDepartment, Accent.Nutrition, Modifier.weight(1f)) { onNavigate(Dest.Food.route) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricStat("Steps", log?.steps?.toString() ?: "—", null, Icons.Filled.DirectionsWalk, Accent.Cardio, Modifier.weight(1f)) { onNavigate(Dest.Daily.route) }
                MetricStat("Water", formatWater(log?.waterMl, s.waterUnit), null, Icons.Filled.WaterDrop, Accent.CardioSoft, Modifier.weight(1f)) { onNavigate(Dest.Daily.route) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricStat("Sleep", log?.sleepHours?.toString() ?: "—", if (log?.sleepHours != null) "hrs" else null, Icons.Filled.Bedtime, Accent.Strength, Modifier.weight(1f)) { onNavigate(Dest.Daily.route) }
                MetricStat("Caffeine", log?.caffeineMg?.toString() ?: "—", if (log?.caffeineMg != null) "mg" else null, Icons.Filled.LocalCafe, Accent.Nutrition600, Modifier.weight(1f)) { onNavigate(Dest.Daily.route) }
            }

            // Today's nutrition (macros).
            val protein = meals.sumOf { it.computedProteinG ?: 0.0 }
            val carbs = meals.sumOf { it.computedCarbsG ?: 0.0 }
            val fat = meals.sumOf { it.computedFatG ?: 0.0 }
            if (protein + carbs + fat > 0 || totalCalories > 0) {
                Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Food.route) }) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        SectionHeader(Icons.Filled.LocalFireDepartment, "Today's nutrition", Accent.Nutrition)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            MacroStat("Calories", "$totalCalories", MaterialTheme.colorScheme.onSurface)
                            MacroStat("Protein", "${protein.toInt()}g", Accent.Strength)
                            MacroStat("Carbs", "${carbs.toInt()}g", Accent.Cardio)
                            MacroStat("Fat", "${fat.toInt()}g", Accent.Nutrition)
                        }
                        if (s.proteinTarget > 0) {
                            Text("Protein goal ${protein.toInt()} / ${s.proteinTarget} g", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }

            // Weight trend chart with moving average.
            val logsAsc = recentLogs.sortedBy { it.date }
            val weightPoints = logsAsc.mapNotNull { it.weight?.let { kg -> weightFromMetric(kg, s.weightUnit).toFloat() } }
            if (weightPoints.size >= 2) {
                Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Daily.route) }) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            SectionHeader(Icons.AutoMirrored.Filled.TrendingUp, "Weight trend", MaterialTheme.colorScheme.primary)
                            val change = weightPoints.last() - weightPoints.first()
                            val sign = if (change >= 0) "+" else ""
                            Text("$sign${"%.1f".format(change)} ${weightLabel(s.weightUnit)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        LineChart(points = weightPoints, avg = movingAvg(weightPoints))
                        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            LegendDot(MaterialTheme.colorScheme.primary, "Weight")
                            LegendDot(MaterialTheme.colorScheme.tertiary, "7-day avg")
                        }
                    }
                }
            }

            val stepPoints = logsAsc.map { (it.steps ?: 0).toFloat() }
            if (stepPoints.any { it > 0f }) {
                Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Daily.route) }) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        SectionHeader(Icons.Filled.DirectionsWalk, "Steps", Accent.Cardio)
                        BarChart(stepPoints, barColor = Accent.Cardio)
                    }
                }
            }

            if (s.calorieTarget > 0) {
                Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Food.route) }) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        SectionHeader(Icons.Filled.LocalFireDepartment, "Calories vs target", Accent.Nutrition)
                        Text("$totalCalories / ${s.calorieTarget} kcal", style = MaterialTheme.typography.bodyMedium)
                        TargetProgressBar(totalCalories.toFloat(), s.calorieTarget.toFloat(), fillColor = Accent.Nutrition)
                    }
                }
            }

            // Recent activities.
            Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Train.route) }) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SectionHeader(Icons.Filled.DirectionsRun, "Recent activities", MaterialTheme.colorScheme.primary)
                    if (activities.isEmpty()) {
                        Text("Nothing logged yet.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    } else {
                        activities.forEach { a ->
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(a.name, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                                    Text(
                                        prettyDate(a.date) + (a.durationMins?.let { " · $it min" } ?: ""),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                TypePill(a.activityType, activityColor(a.activityType))
                            }
                        }
                    }
                }
            }

            // Latest measurements.
            Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Body.route) }) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionHeader(Icons.Filled.Straighten, "Latest measurements", Accent.Rest)
                    latest?.let { m ->
                        Text(prettyDate(m.date), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        val parts = listOfNotNull(
                            m.chest?.let { "Chest ${formatMeasurement(it, s.measurementUnit)}" },
                            m.waist?.let { "Waist ${formatMeasurement(it, s.measurementUnit)}" },
                            m.hips?.let { "Hips ${formatMeasurement(it, s.measurementUnit)}" },
                        )
                        Text(if (parts.isEmpty()) "—" else parts.joinToString(" · "), style = MaterialTheme.typography.bodyMedium)
                    } ?: Text("No measurements yet.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            // Latest progress photo (local cache only).
            photo?.localPath?.takeIf { File(it).exists() }?.let { path ->
                Card(Modifier.fillMaxWidth().clickable { onNavigate(Dest.Photos.route) }) {
                    Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        AsyncImage(
                            model = File(path),
                            contentDescription = "Latest progress photo",
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.size(64.dp).clip(RoundedCornerShape(8.dp)),
                        )
                        Column {
                            Text("Latest photo", style = MaterialTheme.typography.titleMedium)
                            Text(
                                "${photo!!.view} · ${prettyDate(photo!!.date)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun formatWeightValue(kg: Double?, unit: String): String =
    if (kg == null) "—" else weightFromMetric(kg, unit).let { "%.2f".format(it) }

private fun weightUnitOrNull(kg: Double?, unit: String): String? =
    if (kg == null) null else weightLabel(unit)

@Composable
private fun MacroStat(label: String, value: String, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun LegendDot(color: androidx.compose.ui.graphics.Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        androidx.compose.foundation.Canvas(Modifier.size(10.dp)) { drawCircle(color) }
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
