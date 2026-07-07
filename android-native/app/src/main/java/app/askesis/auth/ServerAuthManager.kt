package app.askesis.auth

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import app.askesis.data.prefs.SettingsStore
import app.askesis.data.sync.ServerApi
import kotlinx.coroutines.flow.first

/**
 * Handles authentication to the self-hosted FastAPI server.
 *
 * Flow (reuses the server's existing native OAuth path — no server code change):
 *  1. [startLogin] opens the system browser (Chrome Custom Tab) at `<server>/auth/mobile/login`.
 *  2. The user signs in with Google; the server redirects to the deep link
 *     `app.askesis://auth/callback#token=<jwt>`.
 *  3. `MainActivity` receives that intent and calls [handleRedirect], which stores the JWT and
 *     flips the active sync backend to "server".
 *  4. [refresh] silently re-ups an expired JWT via `POST /auth/refresh` (7-day server grace).
 */
class ServerAuthManager(
    private val context: Context,
    private val settings: SettingsStore,
    private val api: ServerApi = ServerApi(),
) {
    /** Open the server's mobile-login page in a Custom Tab. Requires a non-blank server URL. */
    fun startLogin(serverUrl: String) {
        val custom = CustomTabsIntent.Builder().build()
        custom.intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        custom.launchUrl(context, Uri.parse("$serverUrl/auth/mobile/login"))
    }

    /**
     * If [uri] is our OAuth deep link carrying `#token=<jwt>`, store the JWT and switch to the
     * server backend. Returns true when a token was captured.
     */
    suspend fun handleRedirect(uri: Uri?): Boolean {
        if (uri == null || uri.scheme != REDIRECT_SCHEME || uri.host != REDIRECT_HOST) return false
        val fragment = uri.encodedFragment ?: return false
        val token = fragment.split("&")
            .firstOrNull { it.startsWith("token=") }
            ?.substringAfter("token=")
            ?.let { Uri.decode(it) }
            ?.takeIf { it.isNotBlank() }
            ?: return false
        settings.setAuthToken(token)
        settings.setSyncBackend("server")
        return true
    }

    /** Silently renew the stored JWT. Returns true on success. */
    suspend fun refresh(): Boolean {
        val s = settings.settings.first()
        if (s.serverUrl.isBlank() || s.authToken.isBlank()) return false
        val fresh = api.refresh(s.serverUrl, s.authToken) ?: return false
        settings.setAuthToken(fresh)
        return true
    }

    companion object {
        const val REDIRECT_SCHEME = "app.askesis"
        const val REDIRECT_HOST = "auth"
    }
}
