package app.askesis.data.sync

import app.askesis.auth.GoogleAuthManager
import app.askesis.data.local.AppDatabase
import app.askesis.data.local.entity.ActivityEntity
import app.askesis.data.local.entity.DailyLogEntity
import app.askesis.data.local.entity.FoodEntity
import app.askesis.data.local.entity.MealEntity
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.local.entity.PhotoEntity
import app.askesis.data.prefs.SettingsStore
import kotlinx.coroutines.flow.first
import java.io.File

/**
 * Two-way sync between the on-device Room DB and a user-supplied Google Sheet.
 *
 * Model: one tab per entity. For each tab we pull the full sheet, merge into Room with
 * last-write-wins by `updatedAt` (and honoring `deleted` tombstones), then rewrite the
 * whole tab from the merged local state. Simple and convergent for personal, low-write
 * use. (A concurrent edit on another device between our read and write can be clobbered;
 * acceptable here — see README.)
 */
class SyncEngine(
    private val db: AppDatabase,
    private val api: SheetsApi,
    private val drive: DriveApi,
    private val auth: GoogleAuthManager,
    private val settings: SettingsStore,
    private val photosDir: File,
) : SyncBackend {

    sealed interface Result {
        data class Success(val syncedAt: Long) : Result
        data class Failure(val message: String) : Result
    }

    /** Describes how one entity maps to a sheet tab and to its Room DAO. */
    private class Table<E>(
        val tab: String,
        val headers: List<String>,
        val toRow: (E) -> List<String>,
        val fromRow: (Map<String, String>) -> E,
        val uidOf: (E) -> String,
        val updatedAtOf: (E) -> Long,
        val allRows: suspend () -> List<E>,
        val upsert: suspend (E) -> Unit,
        val markAllClean: suspend () -> Unit,
    )

    private fun tables(): List<Table<*>> = listOf(
        Table(
            tab = "DailyLogs",
            headers = listOf(
                "uid", "date", "weight", "sleepHours", "steps", "waterMl",
                "feelings", "caffeineMg", "ateOutside", "notes", "updatedAt", "deleted"
            ),
            toRow = { e: DailyLogEntity ->
                listOf(
                    e.uid, e.date, R.dbl(e.weight), R.dbl(e.sleepHours), R.int(e.steps),
                    R.int(e.waterMl), R.str(e.feelings), R.int(e.caffeineMg),
                    R.bool(e.ateOutside), R.str(e.notes), e.updatedAt.toString(), e.deleted.toString()
                )
            },
            fromRow = { m ->
                DailyLogEntity(
                    uid = m.getValue("uid"), date = m["date"].orEmpty(),
                    weight = R.toD(m["weight"]), sleepHours = R.toD(m["sleepHours"]),
                    steps = R.toI(m["steps"]), waterMl = R.toI(m["waterMl"]),
                    feelings = R.toS(m["feelings"]), caffeineMg = R.toI(m["caffeineMg"]),
                    ateOutside = R.toB(m["ateOutside"]), notes = R.toS(m["notes"]),
                    updatedAt = R.toL(m["updatedAt"]), dirty = false, deleted = R.toBool(m["deleted"])
                )
            },
            uidOf = { it.uid }, updatedAtOf = { it.updatedAt },
            allRows = { db.dailyLogDao().allRows() },
            upsert = { db.dailyLogDao().upsert(it) },
            markAllClean = { db.dailyLogDao().markAllClean() },
        ),
        Table(
            tab = "Measurements",
            headers = listOf(
                "uid", "date", "neck", "shoulders", "chest", "bicepLeft", "bicepRight",
                "forearmLeft", "forearmRight", "waist", "abdomen", "hips", "thighLeft",
                "thighRight", "calfLeft", "calfRight", "notes", "updatedAt", "deleted"
            ),
            toRow = { e: MeasurementEntity ->
                listOf(
                    e.uid, e.date, R.dbl(e.neck), R.dbl(e.shoulders), R.dbl(e.chest),
                    R.dbl(e.bicepLeft), R.dbl(e.bicepRight), R.dbl(e.forearmLeft),
                    R.dbl(e.forearmRight), R.dbl(e.waist), R.dbl(e.abdomen), R.dbl(e.hips),
                    R.dbl(e.thighLeft), R.dbl(e.thighRight), R.dbl(e.calfLeft),
                    R.dbl(e.calfRight), R.str(e.notes), e.updatedAt.toString(), e.deleted.toString()
                )
            },
            fromRow = { m ->
                MeasurementEntity(
                    uid = m.getValue("uid"), date = m["date"].orEmpty(),
                    neck = R.toD(m["neck"]), shoulders = R.toD(m["shoulders"]), chest = R.toD(m["chest"]),
                    bicepLeft = R.toD(m["bicepLeft"]), bicepRight = R.toD(m["bicepRight"]),
                    forearmLeft = R.toD(m["forearmLeft"]), forearmRight = R.toD(m["forearmRight"]),
                    waist = R.toD(m["waist"]), abdomen = R.toD(m["abdomen"]), hips = R.toD(m["hips"]),
                    thighLeft = R.toD(m["thighLeft"]), thighRight = R.toD(m["thighRight"]),
                    calfLeft = R.toD(m["calfLeft"]), calfRight = R.toD(m["calfRight"]),
                    notes = R.toS(m["notes"]), updatedAt = R.toL(m["updatedAt"]),
                    dirty = false, deleted = R.toBool(m["deleted"])
                )
            },
            uidOf = { it.uid }, updatedAtOf = { it.updatedAt },
            allRows = { db.measurementDao().allRows() },
            upsert = { db.measurementDao().upsert(it) },
            markAllClean = { db.measurementDao().markAllClean() },
        ),
        Table(
            tab = "Activities",
            headers = listOf(
                "uid", "date", "name", "activityType", "timeOfDay", "durationMins",
                "calories", "distanceKm", "url", "notes", "tags", "icon", "exercisesJson",
                "updatedAt", "deleted"
            ),
            toRow = { e: ActivityEntity ->
                listOf(
                    e.uid, e.date, e.name, e.activityType, R.str(e.timeOfDay),
                    R.int(e.durationMins), R.int(e.calories), R.dbl(e.distanceKm),
                    R.str(e.url), R.str(e.notes), R.str(e.tags), R.str(e.icon),
                    R.str(e.exercisesJson), e.updatedAt.toString(), e.deleted.toString()
                )
            },
            fromRow = { m ->
                ActivityEntity(
                    uid = m.getValue("uid"), date = m["date"].orEmpty(), name = m["name"].orEmpty(),
                    activityType = m["activityType"].orEmpty().ifBlank { "cardio" },
                    timeOfDay = R.toS(m["timeOfDay"]), durationMins = R.toI(m["durationMins"]),
                    calories = R.toI(m["calories"]), distanceKm = R.toD(m["distanceKm"]),
                    url = R.toS(m["url"]), notes = R.toS(m["notes"]), tags = R.toS(m["tags"]),
                    icon = R.toS(m["icon"]), exercisesJson = R.toS(m["exercisesJson"]),
                    updatedAt = R.toL(m["updatedAt"]), dirty = false, deleted = R.toBool(m["deleted"])
                )
            },
            uidOf = { it.uid }, updatedAtOf = { it.updatedAt },
            allRows = { db.activityDao().allRows() },
            upsert = { db.activityDao().upsert(it) },
            markAllClean = { db.activityDao().markAllClean() },
        ),
        Table(
            tab = "Meals",
            headers = listOf(
                "uid", "date", "label", "time", "calories", "description", "foodItemsJson",
                "computedCalories", "computedProteinG", "computedCarbsG", "computedFatG",
                "updatedAt", "deleted"
            ),
            toRow = { e: MealEntity ->
                listOf(
                    e.uid, e.date, e.label, R.str(e.time), R.int(e.calories), R.str(e.description),
                    R.str(e.foodItemsJson), R.dbl(e.computedCalories), R.dbl(e.computedProteinG),
                    R.dbl(e.computedCarbsG), R.dbl(e.computedFatG), e.updatedAt.toString(), e.deleted.toString()
                )
            },
            fromRow = { m ->
                MealEntity(
                    uid = m.getValue("uid"), date = m["date"].orEmpty(), label = m["label"].orEmpty(),
                    time = R.toS(m["time"]), calories = R.toI(m["calories"]),
                    description = R.toS(m["description"]), foodItemsJson = R.toS(m["foodItemsJson"]),
                    computedCalories = R.toD(m["computedCalories"]), computedProteinG = R.toD(m["computedProteinG"]),
                    computedCarbsG = R.toD(m["computedCarbsG"]), computedFatG = R.toD(m["computedFatG"]),
                    updatedAt = R.toL(m["updatedAt"]), dirty = false, deleted = R.toBool(m["deleted"])
                )
            },
            uidOf = { it.uid }, updatedAtOf = { it.updatedAt },
            allRows = { db.mealDao().allRows() },
            upsert = { db.mealDao().upsert(it) },
            markAllClean = { db.mealDao().markAllClean() },
        ),
        Table(
            tab = "Foods",
            headers = listOf(
                "uid", "name", "brand", "category", "servingSize", "servingUnit", "calories",
                "proteinG", "carbsG", "fatG", "fiberG", "isShared", "source", "updatedAt", "deleted"
            ),
            toRow = { e: FoodEntity ->
                listOf(
                    e.uid, e.name, R.str(e.brand), R.str(e.category), R.dbl(e.servingSize),
                    R.str(e.servingUnit), R.dbl(e.calories), R.dbl(e.proteinG), R.dbl(e.carbsG),
                    R.dbl(e.fatG), R.dbl(e.fiberG), e.isShared.toString(), R.str(e.source),
                    e.updatedAt.toString(), e.deleted.toString()
                )
            },
            fromRow = { m ->
                FoodEntity(
                    uid = m.getValue("uid"), name = m["name"].orEmpty(), brand = R.toS(m["brand"]),
                    category = R.toS(m["category"]), servingSize = R.toD(m["servingSize"]),
                    servingUnit = R.toS(m["servingUnit"]), calories = R.toD(m["calories"]),
                    proteinG = R.toD(m["proteinG"]), carbsG = R.toD(m["carbsG"]), fatG = R.toD(m["fatG"]),
                    fiberG = R.toD(m["fiberG"]), isShared = R.toBool(m["isShared"]), source = R.toS(m["source"]),
                    updatedAt = R.toL(m["updatedAt"]), dirty = false, deleted = R.toBool(m["deleted"])
                )
            },
            uidOf = { it.uid }, updatedAtOf = { it.updatedAt },
            allRows = { db.foodDao().allRows() },
            upsert = { db.foodDao().upsert(it) },
            markAllClean = { db.foodDao().markAllClean() },
        ),
    )

    /** Run a full sync of every tab. Now-timestamped by the caller-provided [nowMillis]. */
    override suspend fun sync(nowMillis: Long): Result {
        val cfg = settings.settings.first()
        if (cfg.spreadsheetId.isBlank()) {
            return Result.Failure("No spreadsheet configured. Add a Sheet ID in Settings.")
        }
        if (auth.currentAccount() == null) {
            return Result.Failure("Not signed in to Google.")
        }
        return try {
            val token = auth.accessToken()
            for (table in tables()) {
                syncTable(cfg.spreadsheetId, token, table)
            }
            syncPhotos(cfg.spreadsheetId, token)
            settings.setLastSyncAt(nowMillis)
            Result.Success(nowMillis)
        } catch (e: SheetsApi.SheetsException) {
            Result.Failure(
                if (e.code == 403 || e.code == 401) "Access denied. Check the sheet is shared with your account."
                else "Sync failed (${e.code}): ${e.message}"
            )
        } catch (e: Exception) {
            Result.Failure("Sync failed: ${e.message ?: e::class.simpleName}")
        }
    }

    private suspend fun <E> syncTable(spreadsheetId: String, token: String, t: Table<E>) {
        api.ensureSheet(spreadsheetId, token, t.tab)

        // ── Pull ──
        val raw = api.readValues(spreadsheetId, token, "${t.tab}!A1:ZZ")
        val remote: List<E> = if (raw.size > 1) {
            val header = raw.first()
            raw.drop(1).mapNotNull { row ->
                val map = header.indices.associate { i -> header[i] to row.getOrElse(i) { "" } }
                if (map["uid"].isNullOrBlank()) null else t.fromRow(map)
            }
        } else emptyList()

        // ── Merge (last-write-wins) ──
        val localByUid = t.allRows().associateBy(t.uidOf)
        for (r in remote) {
            val local = localByUid[t.uidOf(r)]
            if (local == null || t.updatedAtOf(r) > t.updatedAtOf(local)) {
                t.upsert(r)
            }
        }

        // ── Push merged local state back to the tab ──
        val merged = t.allRows()
        val values = ArrayList<List<String>>(merged.size + 1)
        values.add(t.headers)
        merged.forEach { values.add(t.toRow(it)) }
        api.clearValues(spreadsheetId, token, "${t.tab}!A:ZZ")
        api.updateValues(spreadsheetId, token, "${t.tab}!A1", values)
        t.markAllClean()
    }

    /**
     * Photos are special: the metadata (uid/date/view/driveFileId/notes) lives in a sheet
     * tab like everything else, but the image bytes live in Google Drive. `localPath` is
     * the device-local cache and is never written to the sheet. Each sync, we first push
     * any new local images up to Drive (stamping their `driveFileId`), then sync metadata
     * the same way as the other tabs.
     */
    private suspend fun syncPhotos(spreadsheetId: String, token: String) {
        val tab = "Photos"
        val headers = listOf("uid", "date", "view", "driveFileId", "notes", "updatedAt", "deleted")
        api.ensureSheet(spreadsheetId, token, tab)

        // ── Upload pending image bytes, and reap Drive files for deleted rows ──
        for (p in db.photoDao().allRows()) {
            if (p.deleted) {
                p.driveFileId?.let { runCatching { drive.deleteFile(token, it) } }
            } else if (p.driveFileId == null && p.localPath != null) {
                val file = File(p.localPath)
                if (file.exists()) {
                    val id = drive.uploadFile(token, "askesis-${p.uid}.jpg", file.readBytes())
                    db.photoDao().upsert(p.copy(driveFileId = id))
                }
            }
        }

        // ── Pull metadata ──
        val raw = api.readValues(spreadsheetId, token, "$tab!A1:ZZ")
        val remote: List<PhotoEntity> = if (raw.size > 1) {
            val header = raw.first()
            raw.drop(1).mapNotNull { row ->
                val m = header.indices.associate { i -> header[i] to row.getOrElse(i) { "" } }
                if (m["uid"].isNullOrBlank()) null
                else PhotoEntity(
                    uid = m.getValue("uid"), date = m["date"].orEmpty(),
                    view = m["view"].orEmpty().ifBlank { "front" },
                    driveFileId = R.toS(m["driveFileId"]), localPath = null,
                    notes = R.toS(m["notes"]), updatedAt = R.toL(m["updatedAt"]),
                    dirty = false, deleted = R.toBool(m["deleted"]),
                )
            }
        } else emptyList()

        // ── Merge (last-write-wins), preserving the device-local file path ──
        val localByUid = db.photoDao().allRows().associateBy { it.uid }
        for (r in remote) {
            val local = localByUid[r.uid]
            if (local == null || r.updatedAt > local.updatedAt) {
                db.photoDao().upsert(r.copy(localPath = local?.localPath ?: r.localPath))
            }
        }

        // ── Push merged metadata back ──
        val merged = db.photoDao().allRows()
        val values = ArrayList<List<String>>(merged.size + 1)
        values.add(headers)
        merged.forEach { e ->
            values.add(
                listOf(
                    e.uid, e.date, e.view, R.str(e.driveFileId), R.str(e.notes),
                    e.updatedAt.toString(), e.deleted.toString()
                )
            )
        }
        api.clearValues(spreadsheetId, token, "$tab!A:ZZ")
        api.updateValues(spreadsheetId, token, "$tab!A1", values)
        db.photoDao().markAllClean()
    }

    /** Download a photo's bytes from Drive into the local cache; returns the cached path. */
    override suspend fun fetchPhotoBytes(uid: String): String? {
        val p = db.photoDao().byUid(uid) ?: return null
        if (p.localPath != null && File(p.localPath).exists()) return p.localPath
        val fileId = p.driveFileId ?: return null
        if (auth.currentAccount() == null) return null
        val token = auth.accessToken()
        val bytes = drive.downloadFile(token, fileId)
        photosDir.mkdirs()
        val file = File(photosDir, "$uid.jpg")
        file.writeBytes(bytes)
        db.photoDao().upsert(p.copy(localPath = file.absolutePath))
        return file.absolutePath
    }

    /** Cell (de)serialization helpers. Blank string == null. */
    private object R {
        fun str(v: String?) = v ?: ""
        fun int(v: Int?) = v?.toString() ?: ""
        fun dbl(v: Double?) = v?.toString() ?: ""
        fun bool(v: Boolean?) = v?.toString() ?: ""

        fun toS(v: String?) = v?.takeIf { it.isNotBlank() }
        fun toI(v: String?) = v?.takeIf { it.isNotBlank() }?.toDoubleOrNull()?.toInt()
        fun toD(v: String?) = v?.takeIf { it.isNotBlank() }?.toDoubleOrNull()
        fun toL(v: String?) = v?.takeIf { it.isNotBlank() }?.toDoubleOrNull()?.toLong() ?: 0L
        fun toB(v: String?): Boolean? = v?.takeIf { it.isNotBlank() }?.let { it == "true" || it == "1" }
        fun toBool(v: String?): Boolean = v?.let { it == "true" || it == "1" } ?: false
    }
}
