package app.askesis.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import app.askesis.data.local.dao.ActivityDao
import app.askesis.data.local.dao.DailyLogDao
import app.askesis.data.local.dao.FoodDao
import app.askesis.data.local.dao.MealDao
import app.askesis.data.local.dao.MeasurementDao
import app.askesis.data.local.dao.PhotoDao
import app.askesis.data.local.entity.ActivityEntity
import app.askesis.data.local.entity.DailyLogEntity
import app.askesis.data.local.entity.FoodEntity
import app.askesis.data.local.entity.MealEntity
import app.askesis.data.local.entity.MeasurementEntity
import app.askesis.data.local.entity.PhotoEntity

@Database(
    entities = [
        DailyLogEntity::class,
        MeasurementEntity::class,
        ActivityEntity::class,
        MealEntity::class,
        FoodEntity::class,
        PhotoEntity::class,
    ],
    version = 2,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun dailyLogDao(): DailyLogDao
    abstract fun measurementDao(): MeasurementDao
    abstract fun activityDao(): ActivityDao
    abstract fun mealDao(): MealDao
    abstract fun foodDao(): FoodDao
    abstract fun photoDao(): PhotoDao

    companion object {
        @Volatile private var INSTANCE: AppDatabase? = null

        /** v1 → v2 adds the progress-photos table (Drive-backed). */
        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS photos (
                        uid TEXT NOT NULL PRIMARY KEY,
                        date TEXT NOT NULL,
                        view TEXT NOT NULL,
                        driveFileId TEXT,
                        localPath TEXT,
                        notes TEXT,
                        updatedAt INTEGER NOT NULL DEFAULT 0,
                        dirty INTEGER NOT NULL DEFAULT 0,
                        deleted INTEGER NOT NULL DEFAULT 0
                    )
                    """.trimIndent()
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_photos_date ON photos(date)")
            }
        }

        fun get(context: Context): AppDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "askesis.db"
                ).addMigrations(MIGRATION_1_2)
                    .fallbackToDestructiveMigration()
                    .build().also { INSTANCE = it }
            }
    }
}
