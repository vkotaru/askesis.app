package app.askesis.data.repo

import app.askesis.data.local.AppDatabase
import app.askesis.data.local.entity.ActivityEntity
import app.askesis.data.local.entity.DailyLogEntity
import app.askesis.data.local.entity.FoodEntity
import app.askesis.data.local.entity.MealEntity
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.local.entity.PhotoEntity
import app.askesis.data.prefs.SettingsStore
import app.askesis.data.sync.SyncController
import app.askesis.data.sync.SyncEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

/**
 * Single entry point the UI uses for data. All writes go to Room immediately (instant,
 * offline) and are stamped dirty + updatedAt so the next [sync] pushes them to Sheets.
 */
class AskesisRepository(
    private val db: AppDatabase,
    private val sync: SyncController,
    val settings: SettingsStore,
    private val photosDir: File,
) {
    private fun now() = System.currentTimeMillis()
    private fun newUid() = UUID.randomUUID().toString()

    /** Observable progress/result of the most recent sync. */
    val syncState = sync.state

    // ── Daily logs ────────────────────────────────────────────────────────────
    fun observeDailyLog(date: String): Flow<DailyLogEntity?> = db.dailyLogDao().observeByDate(date)
    fun observeRecentLogs(limit: Int = 60): Flow<List<DailyLogEntity>> = db.dailyLogDao().observeRecent(limit)
    suspend fun dailyLog(date: String): DailyLogEntity? = db.dailyLogDao().byDate(date)

    /** Upsert keyed by date — reuses the existing row's uid so it maps to one sheet row. */
    suspend fun saveDailyLog(draft: DailyLogEntity) {
        val existing = db.dailyLogDao().byDate(draft.date)
        db.dailyLogDao().upsert(
            draft.copy(
                uid = existing?.uid ?: newUid(),
                updatedAt = now(), dirty = true, deleted = false,
            )
        )
    }

    // ── Measurements ──────────────────────────────────────────────────────────
    fun observeRecentMeasurements(limit: Int = 60): Flow<List<MeasurementEntity>> =
        db.measurementDao().observeRecent(limit)
    suspend fun measurement(date: String): MeasurementEntity? = db.measurementDao().byDate(date)
    suspend fun latestMeasurement(): MeasurementEntity? = db.measurementDao().latest()

    suspend fun saveMeasurement(draft: MeasurementEntity) {
        val existing = db.measurementDao().byDate(draft.date)
        db.measurementDao().upsert(
            draft.copy(
                uid = existing?.uid ?: newUid(),
                updatedAt = now(), dirty = true, deleted = false,
            )
        )
    }

    // ── Activities ────────────────────────────────────────────────────────────
    fun observeRecentActivities(limit: Int = 100): Flow<List<ActivityEntity>> =
        db.activityDao().observeRecent(limit)
    fun observeActivitiesForDate(date: String): Flow<List<ActivityEntity>> =
        db.activityDao().observeByDate(date)

    suspend fun saveActivity(draft: ActivityEntity) {
        db.activityDao().upsert(
            draft.copy(
                uid = draft.uid.ifBlank { newUid() },
                updatedAt = now(), dirty = true, deleted = false,
            )
        )
    }

    suspend fun deleteActivity(uid: String) {
        val e = db.activityDao().byUid(uid) ?: return
        db.activityDao().upsert(e.copy(deleted = true, dirty = true, updatedAt = now()))
    }

    // ── Meals ─────────────────────────────────────────────────────────────────
    fun observeMealsForDate(date: String): Flow<List<MealEntity>> = db.mealDao().observeByDate(date)
    fun observeRecentMeals(limit: Int = 100): Flow<List<MealEntity>> = db.mealDao().observeRecent(limit)

    suspend fun saveMeal(draft: MealEntity) {
        db.mealDao().upsert(
            draft.copy(
                uid = draft.uid.ifBlank { newUid() },
                updatedAt = now(), dirty = true, deleted = false,
            )
        )
    }

    suspend fun deleteMeal(uid: String) {
        val e = db.mealDao().byUid(uid) ?: return
        db.mealDao().upsert(e.copy(deleted = true, dirty = true, updatedAt = now()))
    }

    // ── Foods ─────────────────────────────────────────────────────────────────
    fun observeFoods(): Flow<List<FoodEntity>> = db.foodDao().observeAll()
    suspend fun searchFoods(q: String, category: String = "", limit: Int = 50): List<FoodEntity> =
        db.foodDao().search(q.trim(), category, limit)

    suspend fun saveFood(draft: FoodEntity) {
        db.foodDao().upsert(
            draft.copy(
                uid = draft.uid.ifBlank { newUid() },
                updatedAt = now(), dirty = true, deleted = false,
            )
        )
    }

    suspend fun deleteFood(uid: String) {
        val e = db.foodDao().byUid(uid) ?: return
        db.foodDao().upsert(e.copy(deleted = true, dirty = true, updatedAt = now()))
    }

    // ── Photos ──────────────────────────────────────────────────────────────────
    fun observePhotos(): Flow<List<PhotoEntity>> = db.photoDao().observeAll()
    fun observePhotosForDate(date: String): Flow<List<PhotoEntity>> = db.photoDao().observeByDate(date)
    suspend fun latestPhoto(): PhotoEntity? = db.photoDao().latest()

    /** Persist [bytes] to the local photo cache and record a dirty row for the next sync. */
    suspend fun savePhoto(bytes: ByteArray, date: String, view: String, notes: String? = null) {
        val uid = newUid()
        val path = withContext(Dispatchers.IO) {
            photosDir.mkdirs()
            val file = File(photosDir, "$uid.jpg")
            file.writeBytes(bytes)
            file.absolutePath
        }
        db.photoDao().upsert(
            PhotoEntity(
                uid = uid, date = date, view = view, localPath = path,
                notes = notes?.ifBlank { null }, updatedAt = now(), dirty = true,
            )
        )
    }

    suspend fun deletePhoto(uid: String) {
        val p = db.photoDao().byUid(uid) ?: return
        withContext(Dispatchers.IO) { p.localPath?.let { runCatching { File(it).delete() } } }
        db.photoDao().upsert(p.copy(deleted = true, dirty = true, localPath = null, updatedAt = now()))
    }

    /** Resolve a displayable local path, downloading from Drive on demand if needed. */
    suspend fun ensurePhotoFile(uid: String): String? = sync.fetchPhotoBytes(uid)

    // ── Report ──────────────────────────────────────────────────────────────────
    /** Build a plain-text health summary of the last [days] days for sharing/export. */
    suspend fun buildTextReport(days: Int = 30): String {
        val cutoff = java.time.LocalDate.now().minusDays(days.toLong()).toString() // ISO, lexicographically comparable
        val sb = StringBuilder()
        sb.appendLine("Askesis — last $days days")
        sb.appendLine("Generated ${java.time.LocalDate.now()}")
        sb.appendLine()

        val logs = db.dailyLogDao().allRows()
            .filter { !it.deleted && it.date >= cutoff }.sortedByDescending { it.date }
        if (logs.isNotEmpty()) {
            sb.appendLine("Daily logs")
            logs.forEach { l ->
                val parts = listOfNotNull(
                    l.weight?.let { "${it}kg" }, l.steps?.let { "$it steps" },
                    l.sleepHours?.let { "${it}h sleep" }, l.waterMl?.let { "${it}ml water" },
                    l.feelings,
                )
                sb.appendLine("  ${l.date}: ${parts.joinToString(", ")}")
            }
            logs.mapNotNull { it.weight }.let { w ->
                if (w.isNotEmpty()) sb.appendLine("  Weight range: ${w.min()}–${w.max()} kg")
            }
            sb.appendLine()
        }

        val activities = db.activityDao().allRows()
            .filter { !it.deleted && it.date >= cutoff }.sortedByDescending { it.date }
        if (activities.isNotEmpty()) {
            sb.appendLine("Activities (${activities.size})")
            activities.forEach { a ->
                val parts = listOfNotNull(a.durationMins?.let { "${it}min" }, a.distanceKm?.let { "${it}km" })
                sb.appendLine("  ${a.date}: ${a.name}${if (parts.isEmpty()) "" else " (" + parts.joinToString(", ") + ")"}")
            }
            sb.appendLine()
        }

        val latest = latestMeasurement()
        if (latest != null && latest.date >= cutoff) {
            sb.appendLine("Latest measurements (${latest.date})")
            val parts = listOfNotNull(
                latest.chest?.let { "chest ${it}cm" }, latest.waist?.let { "waist ${it}cm" },
                latest.hips?.let { "hips ${it}cm" },
            )
            sb.appendLine("  ${parts.joinToString(", ")}")
            sb.appendLine()
        }

        if (logs.isEmpty() && activities.isEmpty() && latest == null) {
            sb.appendLine("No entries in this period.")
        }
        return sb.toString()
    }

    // ── Sync ──────────────────────────────────────────────────────────────────
    suspend fun runSync(): SyncEngine.Result = sync.sync(now())
}
