package app.askesis.data.sync

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Wraps [SyncEngine] with an observable [state] so any screen can show sync progress and
 * the result of the last run. A [Mutex] serializes runs so a manual "Sync now" and the
 * background [SyncWorker] can never overlap and clobber each other's sheet writes.
 */
class SyncController(private val engine: SyncEngine) {

    sealed interface State {
        data object Idle : State
        data object Syncing : State
        data class Done(val at: Long) : State
        data class Error(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    private val mutex = Mutex()

    suspend fun sync(nowMillis: Long): SyncEngine.Result = mutex.withLock {
        _state.value = State.Syncing
        val result = engine.sync(nowMillis)
        _state.value = when (result) {
            is SyncEngine.Result.Success -> State.Done(result.syncedAt)
            is SyncEngine.Result.Failure -> State.Error(result.message)
        }
        result
    }

    /** Pass-through for callers that only need byte fetching (photo display). */
    suspend fun fetchPhotoBytes(uid: String): String? = engine.fetchPhotoBytes(uid)
}
