package app.askesis.ui.screens

import android.app.Activity
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import app.askesis.ui.components.AppCard as Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import app.askesis.auth.GoogleAuthManager
import app.askesis.data.prefs.SettingsStore
import app.askesis.data.repo.AskesisRepository
import app.askesis.data.sync.SyncEngine
import app.askesis.ui.authManager
import app.askesis.ui.components.NumberField
import app.askesis.ui.components.PlainField
import app.askesis.ui.components.orBlank
import app.askesis.ui.components.toIntOrNullSafe
import app.askesis.ui.repository
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SettingsViewModel(
    private val repo: AskesisRepository,
    private val auth: GoogleAuthManager,
) : ViewModel() {
    val settings = repo.settings.settings
    var syncing by mutableStateOf(false); private set
    var syncMessage by mutableStateOf<String?>(null); private set

    val signedInAccount: String? get() = auth.currentAccount()?.email

    fun signInIntent() = auth.signInIntent()

    fun handleSignInResult(ok: Boolean, data: android.content.Intent?) = viewModelScope.launch {
        val email = if (ok) auth.accountFromIntent(data)?.email else null
        if (email != null) {
            repo.settings.setAccountName(email)
            syncMessage = "Signed in as $email"
        } else {
            syncMessage = "Sign-in cancelled or failed"
        }
    }

    fun signOut() = viewModelScope.launch {
        auth.signOut()
        repo.settings.clearAccount()
        syncMessage = "Signed out"
    }

    fun setSpreadsheetId(id: String) = viewModelScope.launch { repo.settings.setSpreadsheetId(id) }
    fun setThemeMode(v: String) = viewModelScope.launch { repo.settings.setThemeMode(v) }
    fun setColorScheme(v: String) = viewModelScope.launch { repo.settings.setColorScheme(v) }
    fun setWeightUnit(v: String) = viewModelScope.launch { repo.settings.setWeightUnit(v) }
    fun setMeasurementUnit(v: String) = viewModelScope.launch { repo.settings.setMeasurementUnit(v) }
    fun setDistanceUnit(v: String) = viewModelScope.launch { repo.settings.setDistanceUnit(v) }
    fun setWaterUnit(v: String) = viewModelScope.launch { repo.settings.setWaterUnit(v) }
    fun setCalorieTarget(v: Int) = viewModelScope.launch { repo.settings.setCalorieTarget(v) }
    fun setProteinTarget(v: Int) = viewModelScope.launch { repo.settings.setProteinTarget(v) }

    fun syncNow() = viewModelScope.launch {
        syncing = true
        syncMessage = null
        syncMessage = when (val r = repo.runSync()) {
            is SyncEngine.Result.Success -> "Synced successfully"
            is SyncEngine.Result.Failure -> r.message
        }
        syncing = false
    }

    fun buildReport(onReady: (String) -> Unit) = viewModelScope.launch {
        onReady(repo.buildTextReport())
    }

    companion object {
        val Factory = viewModelFactory {
            initializer { SettingsViewModel(repository(), authManager()) }
        }
    }
}

@Composable
fun SettingsScreen(vm: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory)) {
    val s by vm.settings.collectAsState(initial = SettingsStore.Settings())
    var sheetId by remember(s.spreadsheetId) { mutableStateOf(s.spreadsheetId) }
    val context = LocalContext.current

    val signInLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        vm.handleSignInResult(result.resultCode == Activity.RESULT_OK, result.data)
    }

    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // ── Google account ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Google account", style = MaterialTheme.typography.titleMedium)
                val account = s.accountName.ifBlank { vm.signedInAccount }
                Text(account?.let { "Signed in: $it" } ?: "Not signed in", style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { signInLauncher.launch(vm.signInIntent()) }) {
                        Text(if (account == null) "Sign in with Google" else "Switch account")
                    }
                    if (account != null) {
                        OutlinedButton(onClick = { vm.signOut() }) { Text("Sign out") }
                    }
                }
            }
        }

        // ── Spreadsheet ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Google Sheet", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Paste the spreadsheet ID (the long token in its URL between /d/ and /edit). " +
                        "Share the sheet with your signed-in account with edit access.",
                    style = MaterialTheme.typography.bodySmall,
                )
                PlainField("Spreadsheet ID", sheetId, { sheetId = it })
                Button(
                    onClick = { vm.setSpreadsheetId(sheetId) },
                    enabled = sheetId.trim() != s.spreadsheetId,
                ) { Text("Save Sheet ID") }
            }
        }

        // ── Sync ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Sync", style = MaterialTheme.typography.titleMedium)
                Text(lastSyncedText(s.lastSyncAt), style = MaterialTheme.typography.bodySmall)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(onClick = { vm.syncNow() }, enabled = !vm.syncing) { Text("Sync now") }
                    if (vm.syncing) CircularProgressIndicator(Modifier.padding(4.dp))
                }
                vm.syncMessage?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            }
        }

        // ── Report ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Report", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Export a plain-text summary of your last 30 days and share it via any app.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Button(onClick = {
                    vm.buildReport { text ->
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_SUBJECT, "Askesis report")
                            putExtra(Intent.EXTRA_TEXT, text)
                        }
                        context.startActivity(Intent.createChooser(intent, "Share report"))
                    }
                }) { Text("Export & share") }
            }
        }

        // ── Units ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Units", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Data is stored in metric and converted for display based on your preferences.",
                    style = MaterialTheme.typography.bodySmall,
                )
                UnitRow("Body weight", listOf("kg", "lb"), s.weightUnit) { vm.setWeightUnit(it) }
                UnitRow("Body measurements", listOf("cm", "in"), s.measurementUnit) { vm.setMeasurementUnit(it) }
                UnitRow("Distance", listOf("km", "mi"), s.distanceUnit) { vm.setDistanceUnit(it) }
                UnitRow("Water intake", listOf("ml", "L", "oz", "cups"), s.waterUnit) { vm.setWaterUnit(it) }
            }
        }

        // ── Nutrition goals ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Nutrition goals", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Daily targets shown on the Today dashboard and Nutrition screen. Leave at 0 to hide.",
                    style = MaterialTheme.typography.bodySmall,
                )
                var calorie by remember(s.calorieTarget) { mutableStateOf(if (s.calorieTarget > 0) s.calorieTarget.orBlank() else "") }
                var protein by remember(s.proteinTarget) { mutableStateOf(if (s.proteinTarget > 0) s.proteinTarget.orBlank() else "") }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumberField("Calories (kcal)", calorie, { calorie = it }, Modifier.weight(1f), decimal = false)
                    NumberField("Protein (g)", protein, { protein = it }, Modifier.weight(1f), decimal = false)
                }
                Button(
                    onClick = {
                        vm.setCalorieTarget(calorie.toIntOrNullSafe() ?: 0)
                        vm.setProteinTarget(protein.toIntOrNullSafe() ?: 0)
                    },
                    enabled = (calorie.toIntOrNullSafe() ?: 0) != s.calorieTarget ||
                        (protein.toIntOrNullSafe() ?: 0) != s.proteinTarget,
                ) { Text("Save goals") }
            }
        }

        // ── Appearance ──
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Appearance", style = MaterialTheme.typography.titleMedium)
                Text("Theme", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("system", "light", "dark").forEach { mode ->
                        FilterChip(selected = s.themeMode == mode, onClick = { vm.setThemeMode(mode) }, label = { Text(mode) })
                    }
                }
                HorizontalDivider()
                Text("Color", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("forest", "ocean", "sunset", "lavender", "slate").forEach { c ->
                        FilterChip(selected = s.colorScheme == c, onClick = { vm.setColorScheme(c) }, label = { Text(c) })
                    }
                }
            }
        }
    }
}

private fun lastSyncedText(millis: Long): String =
    if (millis <= 0) "Never synced"
    else "Last synced: " + SimpleDateFormat("MMM d, h:mm a", Locale.getDefault()).format(Date(millis))

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun UnitRow(label: String, options: List<String>, selected: String, onSelect: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            options.forEach { opt ->
                FilterChip(selected = selected == opt, onClick = { onSelect(opt) }, label = { Text(opt) })
            }
        }
    }
}
