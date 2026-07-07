package app.askesis.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.compose.runtime.collectAsState
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.askesis.data.repo.AskesisRepository
import app.askesis.data.sync.SyncController
import app.askesis.ui.components.BrandWordmark
import app.askesis.ui.nav.Dest
import app.askesis.ui.screens.ActivitiesScreen
import app.askesis.ui.screens.DailyLogScreen
import app.askesis.ui.screens.MeasurementsScreen
import app.askesis.ui.screens.NutritionScreen
import app.askesis.ui.screens.PhotosScreen
import app.askesis.ui.screens.SettingsScreen
import app.askesis.ui.screens.TodayScreen
import kotlinx.coroutines.launch

class RootViewModel(private val repo: AskesisRepository) : ViewModel() {
    val syncState = repo.syncState
    fun syncNow() = viewModelScope.launch { repo.runSync() }

    companion object {
        val Factory = viewModelFactory { initializer { RootViewModel(repository()) } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AskesisRoot(vm: RootViewModel = viewModel(factory = RootViewModel.Factory)) {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val syncState by vm.syncState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { BrandWordmark() },
                actions = {
                    SyncAction(syncState, onSync = { vm.syncNow() })
                    IconButton(onClick = { nav.navigate(Dest.SETTINGS) }) {
                        Icon(Icons.Filled.Settings, contentDescription = "Settings")
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                val dest = backStack?.destination
                Dest.bottomBar.forEach { item ->
                    NavigationBarItem(
                        selected = dest?.hierarchy?.any { it.route == item.route } == true,
                        onClick = {
                            nav.navigate(item.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(item.icon, contentDescription = item.label) },
                        label = { Text(item.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = Dest.Today.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(Dest.Today.route) { TodayScreen(onNavigate = { nav.navigate(it) }) }
            composable(Dest.Daily.route) { DailyLogScreen() }
            composable(Dest.Body.route) { MeasurementsScreen() }
            composable(Dest.Train.route) { ActivitiesScreen() }
            composable(Dest.Food.route) { NutritionScreen() }
            composable(Dest.Photos.route) { PhotosScreen() }
            composable(Dest.SETTINGS) { SettingsScreen() }
        }
    }
}

@Composable
private fun SyncAction(state: SyncController.State, onSync: () -> Unit) {
    when (state) {
        is SyncController.State.Syncing ->
            CircularProgressIndicator(Modifier.size(20.dp).padding(end = 4.dp))
        else -> IconButton(onClick = onSync) {
            val (icon, tint, desc) = when (state) {
                is SyncController.State.Done -> Triple(
                    Icons.Filled.CloudDone, MaterialTheme.colorScheme.primary, "Synced — tap to sync again"
                )
                is SyncController.State.Error -> Triple(
                    Icons.Filled.CloudOff, MaterialTheme.colorScheme.error, "Sync failed — tap to retry"
                )
                else -> Triple(
                    Icons.Filled.Sync, MaterialTheme.colorScheme.onSurfaceVariant, "Sync now"
                )
            }
            Icon(icon, contentDescription = desc, tint = tint)
        }
    }
}
