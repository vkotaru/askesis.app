package app.askesis.ui.nav

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.ui.graphics.vector.ImageVector

enum class Dest(val route: String, val label: String, val icon: ImageVector) {
    Today("today", "Today", Icons.Filled.Home),
    Daily("daily", "Log", Icons.Filled.EditNote),
    Body("body", "Body", Icons.Filled.Straighten),
    Train("train", "Train", Icons.AutoMirrored.Filled.DirectionsRun),
    Food("food", "Food", Icons.Filled.Restaurant),
    Photos("photos", "Photos", Icons.Filled.PhotoCamera);

    companion object {
        val bottomBar = entries.toList()
        const val SETTINGS = "settings"
    }
}
