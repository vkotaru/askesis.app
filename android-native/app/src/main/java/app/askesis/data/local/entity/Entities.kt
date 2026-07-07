package app.askesis.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Common sync metadata carried by every record.
 *
 * - [uid]       stable cross-device identity, also the key column in the Google Sheet
 * - [updatedAt] epoch millis of the last local edit; drives last-write-wins on sync
 * - [dirty]     true when the row has local changes not yet pushed to the sheet
 * - [deleted]   tombstone — kept locally and written to the sheet so other devices delete too
 */

@Entity(
    tableName = "daily_logs",
    indices = [Index(value = ["date"], unique = true)]
)
data class DailyLogEntity(
    @PrimaryKey val uid: String,
    val date: String,
    val weight: Double? = null,
    val sleepHours: Double? = null,
    val steps: Int? = null,
    val waterMl: Int? = null,
    val feelings: String? = null,
    val caffeineMg: Int? = null,
    val ateOutside: Boolean? = null,
    val notes: String? = null,
    val updatedAt: Long = 0,
    val dirty: Boolean = false,
    val deleted: Boolean = false,
)

@Entity(
    tableName = "measurements",
    indices = [Index(value = ["date"], unique = true)]
)
data class MeasurementEntity(
    @PrimaryKey val uid: String,
    val date: String,
    val neck: Double? = null,
    val shoulders: Double? = null,
    val chest: Double? = null,
    val bicepLeft: Double? = null,
    val bicepRight: Double? = null,
    val forearmLeft: Double? = null,
    val forearmRight: Double? = null,
    val waist: Double? = null,
    val abdomen: Double? = null,
    val hips: Double? = null,
    val thighLeft: Double? = null,
    val thighRight: Double? = null,
    val calfLeft: Double? = null,
    val calfRight: Double? = null,
    val notes: String? = null,
    val updatedAt: Long = 0,
    val dirty: Boolean = false,
    val deleted: Boolean = false,
)

@Entity(
    tableName = "activities",
    indices = [Index(value = ["date"])]
)
data class ActivityEntity(
    @PrimaryKey val uid: String,
    val date: String,
    val name: String,
    val activityType: String = "cardio", // cardio | strength
    val timeOfDay: String? = null,        // morning | afternoon | evening | night
    val durationMins: Int? = null,
    val calories: Int? = null,
    val distanceKm: Double? = null,
    val url: String? = null,
    val notes: String? = null,
    val tags: String? = null,
    val icon: String? = null,
    val exercisesJson: String? = null,    // strength sets, serialized as JSON
    val updatedAt: Long = 0,
    val dirty: Boolean = false,
    val deleted: Boolean = false,
)

@Entity(
    tableName = "meals",
    indices = [Index(value = ["date"])]
)
data class MealEntity(
    @PrimaryKey val uid: String,
    val date: String,
    val label: String,
    val time: String? = null,
    val calories: Int? = null,
    val description: String? = null,
    val foodItemsJson: String? = null,   // selected foods + quantities, serialized as JSON
    val computedCalories: Double? = null,
    val computedProteinG: Double? = null,
    val computedCarbsG: Double? = null,
    val computedFatG: Double? = null,
    val updatedAt: Long = 0,
    val dirty: Boolean = false,
    val deleted: Boolean = false,
)

@Entity(
    tableName = "photos",
    indices = [Index(value = ["date"])]
)
data class PhotoEntity(
    @PrimaryKey val uid: String,
    val date: String,
    val view: String,                     // front | side | back
    val driveFileId: String? = null,      // set once the bytes are uploaded to Google Drive
    val localPath: String? = null,        // absolute path of the cached JPEG on this device
    val notes: String? = null,
    val updatedAt: Long = 0,
    val dirty: Boolean = false,
    val deleted: Boolean = false,
)

@Entity(tableName = "foods")
data class FoodEntity(
    @PrimaryKey val uid: String,
    val name: String,
    val brand: String? = null,
    val category: String? = null,
    val servingSize: Double? = null,
    val servingUnit: String? = null,
    val calories: Double? = null,
    val proteinG: Double? = null,
    val carbsG: Double? = null,
    val fatG: Double? = null,
    val fiberG: Double? = null,
    val isShared: Boolean = false,
    val source: String? = null,
    val updatedAt: Long = 0,
    val dirty: Boolean = false,
    val deleted: Boolean = false,
)
