package app.askesis.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Upsert
import app.askesis.data.local.entity.ActivityEntity
import app.askesis.data.local.entity.DailyLogEntity
import app.askesis.data.local.entity.FoodEntity
import app.askesis.data.local.entity.MealEntity
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.local.entity.PhotoEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface DailyLogDao {
    @Query("SELECT * FROM daily_logs WHERE deleted = 0 ORDER BY date DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<DailyLogEntity>>

    @Query("SELECT * FROM daily_logs WHERE date = :date AND deleted = 0 LIMIT 1")
    suspend fun byDate(date: String): DailyLogEntity?

    @Query("SELECT * FROM daily_logs WHERE date = :date AND deleted = 0 LIMIT 1")
    fun observeByDate(date: String): Flow<DailyLogEntity?>

    @Upsert
    suspend fun upsert(entity: DailyLogEntity)

    @Query("SELECT * FROM daily_logs")
    suspend fun allRows(): List<DailyLogEntity>

    @Query("UPDATE daily_logs SET dirty = 0")
    suspend fun markAllClean()

    @Query("SELECT * FROM daily_logs WHERE dirty = 1")
    suspend fun dirtyRows(): List<DailyLogEntity>

    @Query("SELECT * FROM daily_logs WHERE serverId = :sid LIMIT 1")
    suspend fun byServerId(sid: Long): DailyLogEntity?

    @Query("UPDATE daily_logs SET serverId = :sid WHERE uid = :uid")
    suspend fun setServerId(uid: String, sid: Long)

    @Query("UPDATE daily_logs SET dirty = 0 WHERE uid IN (:uids)")
    suspend fun clearDirty(uids: List<String>)
}

@Dao
interface MeasurementDao {
    @Query("SELECT * FROM measurements WHERE deleted = 0 ORDER BY date DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<MeasurementEntity>>

    @Query("SELECT * FROM measurements WHERE date = :date AND deleted = 0 LIMIT 1")
    suspend fun byDate(date: String): MeasurementEntity?

    @Query("SELECT * FROM measurements WHERE deleted = 0 ORDER BY date DESC LIMIT 1")
    suspend fun latest(): MeasurementEntity?

    @Upsert
    suspend fun upsert(entity: MeasurementEntity)

    @Query("SELECT * FROM measurements")
    suspend fun allRows(): List<MeasurementEntity>

    @Query("UPDATE measurements SET dirty = 0")
    suspend fun markAllClean()

    @Query("SELECT * FROM measurements WHERE dirty = 1")
    suspend fun dirtyRows(): List<MeasurementEntity>

    @Query("SELECT * FROM measurements WHERE serverId = :sid LIMIT 1")
    suspend fun byServerId(sid: Long): MeasurementEntity?

    @Query("UPDATE measurements SET serverId = :sid WHERE uid = :uid")
    suspend fun setServerId(uid: String, sid: Long)

    @Query("UPDATE measurements SET dirty = 0 WHERE uid IN (:uids)")
    suspend fun clearDirty(uids: List<String>)
}

@Dao
interface ActivityDao {
    @Query("SELECT * FROM activities WHERE deleted = 0 ORDER BY date DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<ActivityEntity>>

    @Query("SELECT * FROM activities WHERE date = :date AND deleted = 0 ORDER BY timeOfDay")
    fun observeByDate(date: String): Flow<List<ActivityEntity>>

    @Query("SELECT * FROM activities WHERE uid = :uid LIMIT 1")
    suspend fun byUid(uid: String): ActivityEntity?

    @Upsert
    suspend fun upsert(entity: ActivityEntity)

    @Query("SELECT * FROM activities")
    suspend fun allRows(): List<ActivityEntity>

    @Query("UPDATE activities SET dirty = 0")
    suspend fun markAllClean()

    @Query("SELECT * FROM activities WHERE dirty = 1")
    suspend fun dirtyRows(): List<ActivityEntity>

    @Query("SELECT * FROM activities WHERE serverId = :sid LIMIT 1")
    suspend fun byServerId(sid: Long): ActivityEntity?

    @Query("UPDATE activities SET serverId = :sid WHERE uid = :uid")
    suspend fun setServerId(uid: String, sid: Long)

    @Query("UPDATE activities SET dirty = 0 WHERE uid IN (:uids)")
    suspend fun clearDirty(uids: List<String>)
}

@Dao
interface MealDao {
    @Query("SELECT * FROM meals WHERE date = :date AND deleted = 0 ORDER BY time")
    fun observeByDate(date: String): Flow<List<MealEntity>>

    @Query("SELECT * FROM meals WHERE deleted = 0 ORDER BY date DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<MealEntity>>

    @Query("SELECT * FROM meals WHERE uid = :uid LIMIT 1")
    suspend fun byUid(uid: String): MealEntity?

    @Query("SELECT * FROM meals WHERE date = :date AND deleted = 0")
    suspend fun listByDate(date: String): List<MealEntity>

    @Upsert
    suspend fun upsert(entity: MealEntity)

    @Query("SELECT * FROM meals")
    suspend fun allRows(): List<MealEntity>

    @Query("UPDATE meals SET dirty = 0")
    suspend fun markAllClean()

    @Query("SELECT * FROM meals WHERE dirty = 1")
    suspend fun dirtyRows(): List<MealEntity>

    @Query("SELECT * FROM meals WHERE serverId = :sid LIMIT 1")
    suspend fun byServerId(sid: Long): MealEntity?

    @Query("UPDATE meals SET serverId = :sid WHERE uid = :uid")
    suspend fun setServerId(uid: String, sid: Long)

    @Query("UPDATE meals SET dirty = 0 WHERE uid IN (:uids)")
    suspend fun clearDirty(uids: List<String>)
}

@Dao
interface FoodDao {
    @Query("SELECT * FROM foods WHERE deleted = 0 ORDER BY name")
    fun observeAll(): Flow<List<FoodEntity>>

    @Query("""
        SELECT * FROM foods
        WHERE deleted = 0
          AND (:q = '' OR name LIKE '%' || :q || '%' OR brand LIKE '%' || :q || '%')
          AND (:category = '' OR category = :category)
        ORDER BY name LIMIT :limit
    """)
    suspend fun search(q: String, category: String, limit: Int): List<FoodEntity>

    @Query("SELECT * FROM foods WHERE uid = :uid LIMIT 1")
    suspend fun byUid(uid: String): FoodEntity?

    @Upsert
    suspend fun upsert(entity: FoodEntity)

    @Query("SELECT * FROM foods")
    suspend fun allRows(): List<FoodEntity>

    @Query("UPDATE foods SET dirty = 0")
    suspend fun markAllClean()

    @Query("SELECT * FROM foods WHERE dirty = 1")
    suspend fun dirtyRows(): List<FoodEntity>

    @Query("SELECT * FROM foods WHERE serverId = :sid LIMIT 1")
    suspend fun byServerId(sid: Long): FoodEntity?

    @Query("UPDATE foods SET serverId = :sid WHERE uid = :uid")
    suspend fun setServerId(uid: String, sid: Long)

    @Query("UPDATE foods SET dirty = 0 WHERE uid IN (:uids)")
    suspend fun clearDirty(uids: List<String>)
}

@Dao
interface PhotoDao {
    @Query("SELECT * FROM photos WHERE deleted = 0 ORDER BY date DESC")
    fun observeAll(): Flow<List<PhotoEntity>>

    @Query("SELECT * FROM photos WHERE date = :date AND deleted = 0")
    fun observeByDate(date: String): Flow<List<PhotoEntity>>

    @Query("SELECT * FROM photos WHERE uid = :uid LIMIT 1")
    suspend fun byUid(uid: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE deleted = 0 ORDER BY date DESC LIMIT 1")
    suspend fun latest(): PhotoEntity?

    @Upsert
    suspend fun upsert(entity: PhotoEntity)

    @Query("SELECT * FROM photos")
    suspend fun allRows(): List<PhotoEntity>

    @Query("UPDATE photos SET dirty = 0")
    suspend fun markAllClean()

    @Query("SELECT * FROM photos WHERE dirty = 1")
    suspend fun dirtyRows(): List<PhotoEntity>

    @Query("SELECT * FROM photos WHERE serverId = :sid LIMIT 1")
    suspend fun byServerId(sid: Long): PhotoEntity?

    @Query("UPDATE photos SET serverId = :sid WHERE uid = :uid")
    suspend fun setServerId(uid: String, sid: Long)

    @Query("UPDATE photos SET dirty = 0 WHERE uid IN (:uids)")
    suspend fun clearDirty(uids: List<String>)
}
