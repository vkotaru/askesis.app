package app.askesis.auth

import android.content.Context
import android.content.Intent
import com.google.android.gms.auth.GoogleAuthUtil
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInAccount
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.Scope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext

/**
 * Wraps Google Sign-In and OAuth token retrieval.
 *
 * The app authenticates the user with the Sheets + Drive.file scopes, then exchanges
 * the signed-in account for a short-lived OAuth access token used as a Bearer token
 * against the Sheets/Drive REST APIs. Tokens are cached and refreshed by Play Services.
 */
class GoogleAuthManager(private val context: Context) {

    private val scopeSheets = "https://www.googleapis.com/auth/spreadsheets"
    private val scopeDriveFile = "https://www.googleapis.com/auth/drive.file"

    private val client: GoogleSignInClient by lazy {
        val options = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestEmail()
            .requestScopes(Scope(scopeSheets), Scope(scopeDriveFile))
            .build()
        GoogleSignIn.getClient(context, options)
    }

    fun signInIntent(): Intent = client.signInIntent

    /** Parse the Activity result from [signInIntent]. Returns null on failure/cancel. */
    fun accountFromIntent(data: Intent?): GoogleSignInAccount? =
        try {
            GoogleSignIn.getSignedInAccountFromIntent(data).result
        } catch (_: Exception) {
            null
        }

    fun currentAccount(): GoogleSignInAccount? = GoogleSignIn.getLastSignedInAccount(context)

    suspend fun signOut() {
        try {
            client.signOut().await()
        } catch (_: Exception) {
        }
    }

    /**
     * Fetch a fresh OAuth access token for the signed-in account. Must run off the main
     * thread (handled here via [Dispatchers.IO]). Throws if the user is not signed in or
     * has not granted the required scopes.
     */
    suspend fun accessToken(): String = withContext(Dispatchers.IO) {
        val account = currentAccount()?.account
            ?: throw IllegalStateException("Not signed in")
        val scope = "oauth2:$scopeSheets $scopeDriveFile"
        GoogleAuthUtil.getToken(context, account, scope)
    }
}
