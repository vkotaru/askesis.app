package app.askesis.ui

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.CreationExtras
import app.askesis.AppContainer
import app.askesis.AskesisApp
import app.askesis.auth.GoogleAuthManager
import app.askesis.auth.ServerAuthManager
import app.askesis.data.repo.AskesisRepository

/** The Application container, resolved inside a ViewModel factory. */
fun CreationExtras.container(): AppContainer {
    val app = this[ViewModelProvider.AndroidViewModelFactory.APPLICATION_KEY] as AskesisApp
    return app.container
}

fun CreationExtras.repository(): AskesisRepository = container().repository
fun CreationExtras.authManager(): GoogleAuthManager = container().auth
fun CreationExtras.serverAuthManager(): ServerAuthManager = container().serverAuth
