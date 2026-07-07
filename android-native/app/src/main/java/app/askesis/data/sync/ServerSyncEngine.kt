package app.askesis.data.sync

import app.askesis.auth.ServerAuthManager
import app.askesis.data.local.AppDatabase
import app.askesis.data.local.entity.ActivityEntity
import app.askesis.data.local.entity.DailyLogEntity
import app.askesis.data.local.entity.FoodEntity
import app.askesis.data.local.entity.MealEntity
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.local.entity.PhotoEntity
import app.askesis.data.model.ExerciseSet
import app.askesis.data.model.MealFoodItem
import app.askesis.data.model.Structured
import app.askesis.data.prefs.SettingsStore
import kotlinx.coroutines.flow.first
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID
import kotlin.math.roundToInt

/**
 * Sync backend that reconciles the on-device Room DB with the self-hosted FastAPI server over
 * Tailscale, using the server's delta-sync API (`GET /api/sync/changes` + `POST /api/sync/push`).
 *
 * Each sync: PUSH local `dirty` rows, then PULL server changes since a stored cursor. Identity is
 * bridged via each entity's nullable [serverId] (the server's int PK) ⇄ its local `uid`; daily
 * logs and measurements additionally fall back to matching by `date` (the server upserts those by
 * `(user, date)`). Conflicts use server-wins LWW — on push the server keeps its row if newer; on
 * pull a locally-dirty row is left alone (it will be pushed next round) and otherwise the server
 * row is applied.
 *
 * Offline is unaffected: an unreachable server just yields a [SyncEngine.Result.Failure]; the UI
 * keeps reading/writing Room.
 *
 * Known asymmetry: the server's `/push` ignores meal `food_items`, so phone→server carries only a
 * meal's scalar fields (label/time/calories/description); server→phone pull *does* include the
 * computed food breakdown. Photo bytes go through the authed `/api/photos/...` proxy, not `/push`.
 */
class ServerSyncEngine(
    private val db: AppDatabase,
    private val api: ServerApi,
    private val serverAuth: ServerAuthManager,
    private val settings: SettingsStore,
    private val photosDir: File,
) : SyncBackend {

    private fun newUid() = UUID.randomUUID().toString()

    override suspend fun sync(nowMillis: Long): SyncEngine.Result {
        val cfg = settings.settings.first()
        if (cfg.serverUrl.isBlank()) {
            return SyncEngine.Result.Failure("No server configured. Add the server URL in Settings.")
        }
        return try {
            doSync(cfg.serverUrl, cfg.authToken, nowMillis)
        } catch (e: ServerApi.ServerException) {
            // Expired JWT → try one silent refresh, then retry the whole sync once.
            if (e.code == 401 && serverAuth.refresh()) {
                val fresh = settings.settings.first().authToken
                runCatching { doSync(cfg.serverUrl, fresh, nowMillis) }
                    .getOrElse { SyncEngine.Result.Failure(friendly(it)) }
            } else if (e.code == 401 || e.code == 403) {
                SyncEngine.Result.Failure("Not signed in to the server. Sign in from Settings.")
            } else {
                SyncEngine.Result.Failure("Sync failed (${e.code}): ${e.message}")
            }
        } catch (e: Exception) {
            SyncEngine.Result.Failure(friendly(e))
        }
    }

    private fun friendly(e: Throwable): String = when (e) {
        is ServerApi.ServerException ->
            if (e.code == 401 || e.code == 403) "Not signed in to the server. Sign in from Settings."
            else "Sync failed (${e.code}): ${e.message}"
        else -> "Sync failed: ${e.message ?: e::class.simpleName}"
    }

    private suspend fun doSync(baseUrl: String, token: String, nowMillis: Long): SyncEngine.Result {
        // ── PUSH: batch every dirty scalar row, then handle photos (multipart) separately ──
        val changes = JSONArray()
        val refs = ArrayList<PushRef>()
        pushDailyLogs(changes, refs)
        pushMeasurements(changes, refs)
        pushActivities(changes, refs)
        pushMeals(changes, refs)
        pushFoods(changes, refs)
        if (changes.length() > 0) {
            val results = api.push(baseUrl, token, changes)
            for (i in 0 until results.length()) {
                val r = results.getJSONObject(i)
                val idx = r.optInt("index", -1)
                val ok = r.optBoolean("ok", false)
                val sid = if (r.isNull("serverId")) null else r.optLong("serverId")
                refs.getOrNull(idx)?.onResult?.invoke(ok, sid)
            }
        }
        pushPhotos(baseUrl, token)

        // ── PULL: everything changed since the cursor ──
        val cursor = settings.settings.first().serverSyncCursor
        val since = cursor.ifBlank { "1970-01-01T00:00:00" }
        val resp = api.getChanges(baseUrl, token, since)
        val tracker = CursorTracker(parseIsoUtc(cursor), cursor)
        pullDailyLogs(resp.optJSONArray("dailyLogs"), tracker)
        pullMeasurements(resp.optJSONArray("measurements"), tracker)
        pullActivities(resp.optJSONArray("activities"), tracker)
        pullMeals(resp.optJSONArray("meals"), tracker)
        pullFoods(resp.optJSONArray("foods"), tracker)
        pullPhotos(resp.optJSONArray("photos"), tracker)
        if (tracker.changed) settings.setServerSyncCursor(tracker.iso)

        settings.setLastSyncAt(nowMillis)
        return SyncEngine.Result.Success(nowMillis)
    }

    // ── Push helpers ────────────────────────────────────────────────────────────

    /** A queued change: [onResult] records the server id and clears `dirty` when the push succeeds. */
    private class PushRef(val onResult: suspend (ok: Boolean, serverId: Long?) -> Unit)

    private fun appendChange(
        changes: JSONArray,
        refs: MutableList<PushRef>,
        table: String,
        serverId: Long?,
        deleted: Boolean,
        updatedAt: Long,
        data: JSONObject?,
        setServerId: suspend (Long) -> Unit,
        clearDirty: suspend () -> Unit,
    ) {
        val op = when {
            deleted -> "delete"
            serverId == null -> "create"
            else -> "update"
        }
        val obj = JSONObject()
            .put("table", table)
            .put("operation", op)
            .put("localId", refs.size)
            .put("serverId", serverId ?: JSONObject.NULL)
            .put("data", data ?: JSONObject.NULL)
            .put("timestamp", isoUtc(updatedAt))
        changes.put(obj)
        refs.add(PushRef { ok, sid -> if (ok) { sid?.let { setServerId(it) }; clearDirty() } })
    }

    private suspend fun pushDailyLogs(changes: JSONArray, refs: MutableList<PushRef>) {
        val dao = db.dailyLogDao()
        for (e in dao.dirtyRows()) {
            if (e.deleted && e.serverId == null) { dao.clearDirty(listOf(e.uid)); continue }
            val data = if (e.deleted) null else JSONObject().apply {
                put("date", e.date)
                putOpt("weight", e.weight)
                putOpt("sleep_hours", e.sleepHours)
                putOpt("steps", e.steps)
                putOpt("water_ml", e.waterMl)
                feelingsArray(e.feelings)?.let { put("feelings", it) }
                putOpt("caffeine_mg", e.caffeineMg)
                putOpt("ate_outside", e.ateOutside)
                putOpt("notes", e.notes)
            }
            appendChange(changes, refs, "dailyLogs", e.serverId, e.deleted, e.updatedAt, data,
                { dao.setServerId(e.uid, it) }, { dao.clearDirty(listOf(e.uid)) })
        }
    }

    private suspend fun pushMeasurements(changes: JSONArray, refs: MutableList<PushRef>) {
        val dao = db.measurementDao()
        for (e in dao.dirtyRows()) {
            if (e.deleted && e.serverId == null) { dao.clearDirty(listOf(e.uid)); continue }
            val data = if (e.deleted) null else JSONObject().apply {
                put("date", e.date)
                putOpt("neck", e.neck); putOpt("shoulders", e.shoulders); putOpt("chest", e.chest)
                putOpt("bicep_left", e.bicepLeft); putOpt("bicep_right", e.bicepRight)
                putOpt("forearm_left", e.forearmLeft); putOpt("forearm_right", e.forearmRight)
                putOpt("waist", e.waist); putOpt("abdomen", e.abdomen); putOpt("hips", e.hips)
                putOpt("thigh_left", e.thighLeft); putOpt("thigh_right", e.thighRight)
                putOpt("calf_left", e.calfLeft); putOpt("calf_right", e.calfRight)
                putOpt("notes", e.notes)
            }
            appendChange(changes, refs, "measurements", e.serverId, e.deleted, e.updatedAt, data,
                { dao.setServerId(e.uid, it) }, { dao.clearDirty(listOf(e.uid)) })
        }
    }

    private suspend fun pushActivities(changes: JSONArray, refs: MutableList<PushRef>) {
        val dao = db.activityDao()
        for (e in dao.dirtyRows()) {
            if (e.deleted && e.serverId == null) { dao.clearDirty(listOf(e.uid)); continue }
            val data = if (e.deleted) null else JSONObject().apply {
                put("date", e.date)
                put("name", e.name)
                put("activity_type", e.activityType)
                putOpt("time_of_day", e.timeOfDay)
                putOpt("duration_mins", e.durationMins)
                putOpt("calories", e.calories)
                putOpt("distance_km", e.distanceKm)
                putOpt("url", e.url)
                putOpt("notes", e.notes)
                putOpt("tags", e.tags)
                putOpt("icon", e.icon)
                val exercises = Structured.decodeExercises(e.exercisesJson)
                if (exercises.isNotEmpty()) {
                    val arr = JSONArray()
                    exercises.forEach { s ->
                        arr.put(JSONObject().put("name", s.name)
                            .putOpt("sets", s.sets)
                            .putOpt("reps", s.reps?.toString())
                            .putOpt("weight_kg", s.weight))
                    }
                    put("exercises", arr)
                }
            }
            appendChange(changes, refs, "activities", e.serverId, e.deleted, e.updatedAt, data,
                { dao.setServerId(e.uid, it) }, { dao.clearDirty(listOf(e.uid)) })
        }
    }

    private suspend fun pushMeals(changes: JSONArray, refs: MutableList<PushRef>) {
        val dao = db.mealDao()
        for (e in dao.dirtyRows()) {
            if (e.deleted && e.serverId == null) { dao.clearDirty(listOf(e.uid)); continue }
            // Server /push ignores food_items — send scalar fields only (see class KDoc).
            val data = if (e.deleted) null else JSONObject().apply {
                put("date", e.date)
                put("label", e.label)
                putOpt("time", e.time)
                putOpt("calories", e.calories ?: e.computedCalories?.roundToInt())
                putOpt("description", e.description)
            }
            appendChange(changes, refs, "meals", e.serverId, e.deleted, e.updatedAt, data,
                { dao.setServerId(e.uid, it) }, { dao.clearDirty(listOf(e.uid)) })
        }
    }

    private suspend fun pushFoods(changes: JSONArray, refs: MutableList<PushRef>) {
        val dao = db.foodDao()
        for (e in dao.dirtyRows()) {
            if (e.deleted && e.serverId == null) { dao.clearDirty(listOf(e.uid)); continue }
            val data = if (e.deleted) null else JSONObject().apply {
                put("name", e.name)
                putOpt("brand", e.brand)
                putOpt("category", e.category)
                putOpt("serving_size", e.servingSize)
                putOpt("serving_unit", e.servingUnit)
                putOpt("calories", e.calories)
                putOpt("protein_g", e.proteinG)
                putOpt("carbs_g", e.carbsG)
                putOpt("fat_g", e.fatG)
                putOpt("fiber_g", e.fiberG)
                put("is_shared", e.isShared)
                putOpt("source", e.source)
            }
            appendChange(changes, refs, "foods", e.serverId, e.deleted, e.updatedAt, data,
                { dao.setServerId(e.uid, it) }, { dao.clearDirty(listOf(e.uid)) })
        }
    }

    /** Photos: upload new bytes via the multipart proxy, delete via the REST endpoint. */
    private suspend fun pushPhotos(baseUrl: String, token: String) {
        val dao = db.photoDao()
        for (p in dao.dirtyRows()) {
            when {
                p.deleted && p.serverId != null -> {
                    runCatching { api.deletePhoto(baseUrl, token, p.serverId!!) }
                    dao.clearDirty(listOf(p.uid))
                }
                p.deleted -> dao.clearDirty(listOf(p.uid)) // never reached the server
                p.serverId == null && p.localPath != null -> {
                    val f = File(p.localPath)
                    if (f.exists()) {
                        val id = api.uploadPhoto(baseUrl, token, f.readBytes(), p.date, p.view, p.notes)
                        dao.setServerId(p.uid, id)
                    }
                    dao.clearDirty(listOf(p.uid))
                }
                else -> dao.clearDirty(listOf(p.uid)) // metadata-only edit; no dedicated endpoint
            }
        }
    }

    // ── Pull helpers ──────────────────────────────────────────────────────────────

    private suspend fun pullDailyLogs(arr: JSONArray?, tracker: CursorTracker) {
        val dao = db.dailyLogDao()
        forEachRow(arr, tracker) { o, sid, serverTs, deleted ->
            val date = o.str("date") ?: return@forEachRow
            val existing = dao.byServerId(sid) ?: dao.byDate(date)
            if (deleted) { existing?.let { if (!it.deleted) dao.upsert(it.copy(deleted = true, dirty = false, updatedAt = serverTs, serverId = sid)) else dao.setServerId(it.uid, sid) }; return@forEachRow }
            if (existing?.dirty == true) return@forEachRow
            dao.upsert(
                DailyLogEntity(
                    uid = existing?.uid ?: newUid(), date = date,
                    weight = o.dbl("weight"), sleepHours = o.dbl("sleep_hours"),
                    steps = o.intn("steps"), waterMl = o.intn("water_ml"),
                    feelings = feelingsString(o.optJSONArray("feelings")),
                    caffeineMg = o.intn("caffeine_mg"), ateOutside = o.booln("ate_outside"),
                    notes = o.str("notes"), updatedAt = serverTs, dirty = false,
                    deleted = false, serverId = sid,
                )
            )
        }
    }

    private suspend fun pullMeasurements(arr: JSONArray?, tracker: CursorTracker) {
        val dao = db.measurementDao()
        forEachRow(arr, tracker) { o, sid, serverTs, deleted ->
            val date = o.str("date") ?: return@forEachRow
            val existing = dao.byServerId(sid) ?: dao.byDate(date)
            if (deleted) { existing?.let { if (!it.deleted) dao.upsert(it.copy(deleted = true, dirty = false, updatedAt = serverTs, serverId = sid)) else dao.setServerId(it.uid, sid) }; return@forEachRow }
            if (existing?.dirty == true) return@forEachRow
            dao.upsert(
                MeasurementEntity(
                    uid = existing?.uid ?: newUid(), date = date,
                    neck = o.dbl("neck"), shoulders = o.dbl("shoulders"), chest = o.dbl("chest"),
                    bicepLeft = o.dbl("bicep_left"), bicepRight = o.dbl("bicep_right"),
                    forearmLeft = o.dbl("forearm_left"), forearmRight = o.dbl("forearm_right"),
                    waist = o.dbl("waist"), abdomen = o.dbl("abdomen"), hips = o.dbl("hips"),
                    thighLeft = o.dbl("thigh_left"), thighRight = o.dbl("thigh_right"),
                    calfLeft = o.dbl("calf_left"), calfRight = o.dbl("calf_right"),
                    notes = o.str("notes"), updatedAt = serverTs, dirty = false,
                    deleted = false, serverId = sid,
                )
            )
        }
    }

    private suspend fun pullActivities(arr: JSONArray?, tracker: CursorTracker) {
        val dao = db.activityDao()
        forEachRow(arr, tracker) { o, sid, serverTs, deleted ->
            val existing = dao.byServerId(sid)
            if (deleted) { existing?.let { if (!it.deleted) dao.upsert(it.copy(deleted = true, dirty = false, updatedAt = serverTs, serverId = sid)) }; return@forEachRow }
            if (existing?.dirty == true) return@forEachRow
            val sets = o.optJSONArray("exercises")?.let { ex ->
                (0 until ex.length()).map { i ->
                    val x = ex.getJSONObject(i)
                    ExerciseSet(x.str("name") ?: "", x.intn("sets"), x.str("reps")?.toIntOrNull(), x.dbl("weight_kg"))
                }
            } ?: emptyList()
            dao.upsert(
                ActivityEntity(
                    uid = existing?.uid ?: newUid(), date = o.str("date") ?: return@forEachRow,
                    name = o.str("name") ?: "", activityType = o.str("activity_type") ?: "cardio",
                    timeOfDay = o.str("time_of_day"), durationMins = o.intn("duration_mins"),
                    calories = o.intn("calories"), distanceKm = o.dbl("distance_km"),
                    url = o.str("url"), notes = o.str("notes"), tags = o.str("tags"),
                    icon = o.str("icon"), exercisesJson = Structured.encodeExercises(sets),
                    updatedAt = serverTs, dirty = false, deleted = false, serverId = sid,
                )
            )
        }
    }

    private suspend fun pullMeals(arr: JSONArray?, tracker: CursorTracker) {
        val dao = db.mealDao()
        forEachRow(arr, tracker) { o, sid, serverTs, deleted ->
            val existing = dao.byServerId(sid)
            if (deleted) { existing?.let { if (!it.deleted) dao.upsert(it.copy(deleted = true, dirty = false, updatedAt = serverTs, serverId = sid)) }; return@forEachRow }
            if (existing?.dirty == true) return@forEachRow
            val items = o.optJSONArray("food_items")?.let { fi ->
                (0 until fi.length()).map { i ->
                    val f = fi.getJSONObject(i)
                    val qty = f.dbl("quantity") ?: 1.0
                    fun perServing(k: String) = f.dbl(k)?.let { if (qty > 0) it / qty else it }
                    MealFoodItem(
                        foodUid = f.lng("food_item_id")?.toString() ?: "",
                        name = f.str("food_item_name") ?: "",
                        quantity = qty,
                        calories = perServing("calories"), proteinG = perServing("protein_g"),
                        carbsG = perServing("carbs_g"), fatG = perServing("fat_g"),
                    )
                }
            } ?: emptyList()
            val totals = Structured.totals(items)
            dao.upsert(
                MealEntity(
                    uid = existing?.uid ?: newUid(), date = o.str("date") ?: return@forEachRow,
                    label = o.str("label") ?: "", time = o.str("time"),
                    calories = o.intn("calories"), description = o.str("description"),
                    foodItemsJson = Structured.encodeFoodItems(items),
                    computedCalories = if (items.isEmpty()) null else totals.calories,
                    computedProteinG = if (items.isEmpty()) null else totals.proteinG,
                    computedCarbsG = if (items.isEmpty()) null else totals.carbsG,
                    computedFatG = if (items.isEmpty()) null else totals.fatG,
                    updatedAt = serverTs, dirty = false, deleted = false, serverId = sid,
                )
            )
        }
    }

    private suspend fun pullFoods(arr: JSONArray?, tracker: CursorTracker) {
        val dao = db.foodDao()
        forEachRow(arr, tracker) { o, sid, serverTs, deleted ->
            val existing = dao.byServerId(sid)
            if (deleted) { existing?.let { if (!it.deleted) dao.upsert(it.copy(deleted = true, dirty = false, updatedAt = serverTs, serverId = sid)) }; return@forEachRow }
            if (existing?.dirty == true) return@forEachRow
            dao.upsert(
                FoodEntity(
                    uid = existing?.uid ?: newUid(), name = o.str("name") ?: "",
                    brand = o.str("brand"), category = o.str("category"),
                    servingSize = o.dbl("serving_size"), servingUnit = o.str("serving_unit"),
                    calories = o.dbl("calories"), proteinG = o.dbl("protein_g"),
                    carbsG = o.dbl("carbs_g"), fatG = o.dbl("fat_g"), fiberG = o.dbl("fiber_g"),
                    isShared = o.booln("is_shared") ?: false, source = o.str("source"),
                    updatedAt = serverTs, dirty = false, deleted = false, serverId = sid,
                )
            )
        }
    }

    private suspend fun pullPhotos(arr: JSONArray?, tracker: CursorTracker) {
        val dao = db.photoDao()
        forEachRow(arr, tracker) { o, sid, serverTs, deleted ->
            val existing = dao.byServerId(sid)
            if (deleted) { existing?.let { if (!it.deleted) dao.upsert(it.copy(deleted = true, dirty = false, updatedAt = serverTs, serverId = sid)) }; return@forEachRow }
            if (existing?.dirty == true) return@forEachRow
            dao.upsert(
                PhotoEntity(
                    uid = existing?.uid ?: newUid(), date = o.str("date") ?: return@forEachRow,
                    view = o.str("view") ?: "front", driveFileId = o.str("drive_file_id"),
                    localPath = existing?.localPath, notes = o.str("notes"),
                    updatedAt = serverTs, dirty = false, deleted = false, serverId = sid,
                )
            )
        }
    }

    /** Iterate server rows, advancing [tracker] and decoding common (id, timestamp, deleted). */
    private suspend inline fun forEachRow(
        arr: JSONArray?,
        tracker: CursorTracker,
        body: (o: JSONObject, serverId: Long, serverTs: Long, deleted: Boolean) -> Unit,
    ) {
        if (arr == null) return
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val sid = o.lng("id") ?: continue
            val updatedRaw = o.str("updated_at")
            val deletedRaw = o.str("deleted_at")
            updatedRaw?.let(tracker::offer)
            deletedRaw?.let(tracker::offer)
            val serverTs = maxOf(parseIsoUtc(updatedRaw), parseIsoUtc(deletedRaw))
            body(o, sid, serverTs, deletedRaw != null)
        }
    }

    override suspend fun fetchPhotoBytes(uid: String): String? {
        val p = db.photoDao().byUid(uid) ?: return null
        if (p.localPath != null && File(p.localPath).exists()) return p.localPath
        val sid = p.serverId ?: return null
        val cfg = settings.settings.first()
        if (cfg.serverUrl.isBlank()) return null
        val bytes = try {
            api.downloadPhoto(cfg.serverUrl, cfg.authToken, sid)
        } catch (e: ServerApi.ServerException) {
            if (e.code == 401 && serverAuth.refresh()) {
                api.downloadPhoto(cfg.serverUrl, settings.settings.first().authToken, sid)
            } else return null
        }
        photosDir.mkdirs()
        val file = File(photosDir, "$uid.jpg")
        file.writeBytes(bytes)
        db.photoDao().upsert(p.copy(localPath = file.absolutePath))
        return file.absolutePath
    }

    /** Tracks the greatest server timestamp seen so the next pull can resume just after it. */
    private class CursorTracker(private var millis: Long, var iso: String) {
        var changed = false; private set
        fun offer(rawIso: String) {
            val m = parseIsoUtc(rawIso)
            if (m > millis) { millis = m; iso = rawIso; changed = true }
        }
    }

    private fun feelingsArray(csv: String?): JSONArray? {
        val parts = csv?.split(",")?.map { it.trim() }?.filter { it.isNotBlank() } ?: return null
        if (parts.isEmpty()) return null
        return JSONArray().apply { parts.forEach { put(it) } }
    }

    private fun feelingsString(arr: JSONArray?): String? {
        if (arr == null) return null
        val parts = (0 until arr.length()).map { arr.optString(it) }.filter { it.isNotBlank() }
        return parts.joinToString(",").ifBlank { null }
    }
}

// ── Shared JSON + time helpers (file-private) ─────────────────────────────────────

private fun JSONObject.str(k: String): String? =
    if (has(k) && !isNull(k)) optString(k).ifBlank { null } else null
private fun JSONObject.dbl(k: String): Double? = if (has(k) && !isNull(k)) optDouble(k) else null
private fun JSONObject.intn(k: String): Int? = if (has(k) && !isNull(k)) optInt(k) else null
private fun JSONObject.lng(k: String): Long? = if (has(k) && !isNull(k)) optLong(k) else null
private fun JSONObject.booln(k: String): Boolean? = if (has(k) && !isNull(k)) optBoolean(k) else null

/** Epoch millis → naive-UTC ISO 8601 (millisecond precision), matching the server's format. */
private fun isoUtc(millis: Long): String =
    LocalDateTime.ofEpochSecond(millis / 1000, ((millis % 1000) * 1_000_000).toInt(), ZoneOffset.UTC)
        .toString()

/** Parse a server timestamp (naive UTC, optionally with a Z/offset) to epoch millis. Null/blank → 0. */
private fun parseIsoUtc(s: String?): Long {
    val t = s?.trim().orEmpty()
    if (t.isEmpty()) return 0L
    return runCatching { OffsetDateTime.parse(t).toInstant().toEpochMilli() }
        .recoverCatching { LocalDateTime.parse(t).toInstant(ZoneOffset.UTC).toEpochMilli() }
        .getOrDefault(0L)
}
