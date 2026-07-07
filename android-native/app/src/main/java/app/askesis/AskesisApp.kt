package app.askesis

import android.app.Application
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import app.askesis.auth.GoogleAuthManager
import app.askesis.auth.ServerAuthManager
import app.askesis.data.local.AppDatabase
import app.askesis.data.prefs.SettingsStore
import app.askesis.data.repo.AskesisRepository
import app.askesis.data.sync.DriveApi
import app.askesis.data.sync.ServerApi
import app.askesis.data.sync.ServerSyncEngine
import app.askesis.data.sync.SheetsApi
import app.askesis.data.sync.SyncController
import app.askesis.data.sync.SyncEngine
import app.askesis.data.sync.SyncWorker
import kotlinx.coroutines.flow.first
import java.io.File
import java.util.concurrent.TimeUnit

/** Minimal service locator — one instance of each singleton, wired by hand. */
class AppContainer(app: Application) {
    val db = AppDatabase.get(app)
    val settings = SettingsStore(app)
    val auth = GoogleAuthManager(app)
    val photosDir = File(app.filesDir, "photos")

    // Google Sheets backend
    private val sheetsApi = SheetsApi()
    private val driveApi = DriveApi()
    private val sheetsEngine = SyncEngine(db, sheetsApi, driveApi, auth, settings, photosDir)

    // Self-hosted FastAPI server backend (Tailscale)
    private val serverApi = ServerApi()
    val serverAuth = ServerAuthManager(app, settings, serverApi)
    private val serverEngine = ServerSyncEngine(db, serverApi, serverAuth, settings, photosDir)

    // Pick the active backend per sync from the persisted preference.
    val syncController = SyncController {
        if (settings.settings.first().syncBackend == "server") serverEngine else sheetsEngine
    }
    val repository = AskesisRepository(db, syncController, settings, photosDir)
}

class AskesisApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        schedulePeriodicSync()
    }

    private fun schedulePeriodicSync() {
        val request = PeriodicWorkRequestBuilder<SyncWorker>(3, TimeUnit.HOURS)
            .setConstraints(
                Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            )
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "askesis-periodic-sync",
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }
}
