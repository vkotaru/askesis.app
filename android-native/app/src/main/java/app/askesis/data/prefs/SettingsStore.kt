package app.askesis.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "askesis_settings")

/** Lightweight typed wrapper over DataStore for app + sync configuration. */
class SettingsStore(private val context: Context) {

    data class Settings(
        val spreadsheetId: String = "",
        val accountName: String = "",
        val lastSyncAt: Long = 0,
        val weightUnit: String = "kg",
        val measurementUnit: String = "cm",
        val distanceUnit: String = "km",
        val waterUnit: String = "ml",
        val calorieTarget: Int = 0,          // 0 = unset
        val proteinTarget: Int = 0,          // 0 = unset
        val themeMode: String = "system",   // system | light | dark
        val colorScheme: String = "forest",
    )

    val settings: Flow<Settings> = context.dataStore.data.map { p ->
        Settings(
            spreadsheetId = p[SPREADSHEET_ID] ?: "",
            accountName = p[ACCOUNT_NAME] ?: "",
            lastSyncAt = p[LAST_SYNC_AT] ?: 0,
            weightUnit = p[WEIGHT_UNIT] ?: "kg",
            measurementUnit = p[MEASUREMENT_UNIT] ?: "cm",
            distanceUnit = p[DISTANCE_UNIT] ?: "km",
            waterUnit = p[WATER_UNIT] ?: "ml",
            calorieTarget = p[CALORIE_TARGET] ?: 0,
            proteinTarget = p[PROTEIN_TARGET] ?: 0,
            themeMode = p[THEME_MODE] ?: "system",
            colorScheme = p[COLOR_SCHEME] ?: "forest",
        )
    }

    suspend fun setSpreadsheetId(id: String) = edit { it[SPREADSHEET_ID] = id.trim() }
    suspend fun setAccountName(name: String) = edit { it[ACCOUNT_NAME] = name }
    suspend fun setLastSyncAt(millis: Long) = edit { it[LAST_SYNC_AT] = millis }
    suspend fun setWeightUnit(v: String) = edit { it[WEIGHT_UNIT] = v }
    suspend fun setMeasurementUnit(v: String) = edit { it[MEASUREMENT_UNIT] = v }
    suspend fun setDistanceUnit(v: String) = edit { it[DISTANCE_UNIT] = v }
    suspend fun setWaterUnit(v: String) = edit { it[WATER_UNIT] = v }
    suspend fun setCalorieTarget(v: Int) = edit { it[CALORIE_TARGET] = v }
    suspend fun setProteinTarget(v: Int) = edit { it[PROTEIN_TARGET] = v }
    suspend fun setThemeMode(v: String) = edit { it[THEME_MODE] = v }
    suspend fun setColorScheme(v: String) = edit { it[COLOR_SCHEME] = v }

    suspend fun clearAccount() = context.dataStore.edit {
        it.remove(ACCOUNT_NAME)
        it.remove(LAST_SYNC_AT)
    }

    private suspend fun edit(block: (androidx.datastore.preferences.core.MutablePreferences) -> Unit) {
        context.dataStore.edit(block)
    }

    private companion object {
        val SPREADSHEET_ID = stringPreferencesKey("spreadsheet_id")
        val ACCOUNT_NAME = stringPreferencesKey("account_name")
        val LAST_SYNC_AT = longPreferencesKey("last_sync_at")
        val WEIGHT_UNIT = stringPreferencesKey("weight_unit")
        val MEASUREMENT_UNIT = stringPreferencesKey("measurement_unit")
        val DISTANCE_UNIT = stringPreferencesKey("distance_unit")
        val WATER_UNIT = stringPreferencesKey("water_unit")
        val CALORIE_TARGET = intPreferencesKey("calorie_target")
        val PROTEIN_TARGET = intPreferencesKey("protein_target")
        val THEME_MODE = stringPreferencesKey("theme_mode")
        val COLOR_SCHEME = stringPreferencesKey("color_scheme")
    }
}
