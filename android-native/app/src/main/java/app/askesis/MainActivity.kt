package app.askesis

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.lifecycleScope
import app.askesis.data.prefs.SettingsStore
import app.askesis.ui.AskesisRoot
import app.askesis.ui.theme.AskesisTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as AskesisApp).container
        handleAuthRedirect(intent)
        setContent {
            val settings by container.settings.settings.collectAsState(initial = SettingsStore.Settings())
            AskesisTheme(schemeName = settings.colorScheme, themeMode = settings.themeMode) {
                AskesisRoot()
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleAuthRedirect(intent)
    }

    /** Capture the `app.askesis://auth/callback#token=<jwt>` deep link from the login browser tab. */
    private fun handleAuthRedirect(intent: Intent?) {
        val uri = intent?.data ?: return
        val serverAuth = (application as AskesisApp).container.serverAuth
        lifecycleScope.launch { serverAuth.handleRedirect(uri) }
    }
}
