package app.askesis

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import app.askesis.data.prefs.SettingsStore
import app.askesis.ui.AskesisRoot
import app.askesis.ui.theme.AskesisTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as AskesisApp).container
        setContent {
            val settings by container.settings.settings.collectAsState(initial = SettingsStore.Settings())
            AskesisTheme(schemeName = settings.colorScheme, themeMode = settings.themeMode) {
                AskesisRoot()
            }
        }
    }
}
