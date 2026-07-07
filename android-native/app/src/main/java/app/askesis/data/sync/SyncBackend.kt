package app.askesis.data.sync

/**
 * A sync backend reconciles the on-device Room DB with some remote store. The app ships two:
 *
 * - [SyncEngine]       — Google Sheets (+ Drive for photos), the original backend.
 * - [ServerSyncEngine] — the self-hosted FastAPI server over Tailscale, sharing one Postgres
 *                        source of truth with the web app.
 *
 * Both are pure background reconciliation: the UI always reads/writes Room directly, so the app
 * stays fully functional offline regardless of which backend (if any) is reachable.
 *
 * [SyncController] depends only on this interface and picks the concrete backend at run time
 * from `SettingsStore.syncBackend`.
 */
interface SyncBackend {
    /** Run one full reconciliation, stamping success with [nowMillis]. Never throws. */
    suspend fun sync(nowMillis: Long): SyncEngine.Result

    /** Resolve a displayable local path for a photo, fetching remote bytes on demand. */
    suspend fun fetchPhotoBytes(uid: String): String?
}
