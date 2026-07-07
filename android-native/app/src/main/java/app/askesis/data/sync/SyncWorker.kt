package app.askesis.data.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import app.askesis.AskesisApp

/** Periodic/background sync entry point driven by WorkManager. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val repo = (applicationContext as AskesisApp).container.repository
        return when (val r = repo.runSync()) {
            is SyncEngine.Result.Success -> Result.success()
            is SyncEngine.Result.Failure -> {
                // Retry transient failures; give up only after WorkManager's backoff cap.
                if (r.message.contains("denied") || r.message.contains("No spreadsheet") ||
                    r.message.contains("Not signed in")
                ) Result.failure() else Result.retry()
            }
        }
    }
}
