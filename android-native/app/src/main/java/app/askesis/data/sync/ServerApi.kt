package app.askesis.data.sync

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Thin client over the self-hosted Askesis FastAPI server (reached over Tailscale).
 *
 * Deliberately dependency-free (HttpURLConnection + org.json), matching [SheetsApi]/[DriveApi].
 * Uses the server's purpose-built offline delta-sync API:
 *   - GET  /api/sync/changes?since=<iso>   pull rows changed since a cursor
 *   - POST /api/sync/push                   push a batch of local mutations
 * plus the photo proxy endpoints and JWT refresh. Auth is a server-issued JWT bearer token.
 */
class ServerApi {

    /** Non-2xx response. [code] 401 signals the JWT is missing/expired (trigger a refresh). */
    class ServerException(val code: Int, message: String) : Exception(message)

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    // ── Delta sync ──────────────────────────────────────────────────────────────

    /** Pull every row changed or soft-deleted after [sinceIso] (naive-UTC ISO 8601). */
    suspend fun getChanges(baseUrl: String, token: String, sinceIso: String): JSONObject =
        withContext(Dispatchers.IO) {
            requestJson("$baseUrl/api/sync/changes?since=${enc(sinceIso)}", "GET", token, null)
        }

    /** Push [changes] (a JSON array of {table, operation, localId, serverId, data, timestamp}). */
    suspend fun push(baseUrl: String, token: String, changes: JSONArray): JSONArray =
        withContext(Dispatchers.IO) {
            val body = JSONObject().put("changes", changes)
            requestJson("$baseUrl/api/sync/push", "POST", token, body)
                .optJSONArray("results") ?: JSONArray()
        }

    // ── Auth ────────────────────────────────────────────────────────────────────

    /** Exchange a still-in-grace JWT for a fresh one. Returns null if the server declines. */
    suspend fun refresh(baseUrl: String, token: String): String? = withContext(Dispatchers.IO) {
        runCatching {
            requestJson("$baseUrl/auth/refresh", "POST", token, JSONObject())
                .optString("access_token").ifBlank { null }
        }.getOrNull()
    }

    // ── Photos (proxy through the server to the owner's Drive) ─────────────────────

    /** Upload progress-photo [bytes]; returns the created photo's server id. */
    suspend fun uploadPhoto(
        baseUrl: String,
        token: String,
        bytes: ByteArray,
        date: String,
        view: String,
        notes: String?,
    ): Long = withContext(Dispatchers.IO) {
        val boundary = "askesisBoundary" + bytes.size + date.hashCode()
        val nl = "\r\n"
        fun field(name: String, value: String) =
            "--$boundary$nl" +
                "Content-Disposition: form-data; name=\"$name\"$nl$nl$value$nl"

        val body = ByteArrayOutputStream().apply {
            write(field("photo_date", date).toByteArray())
            write(field("view", view).toByteArray())
            if (!notes.isNullOrBlank()) write(field("notes", notes).toByteArray())
            write(
                ("--$boundary$nl" +
                    "Content-Disposition: form-data; name=\"file\"; filename=\"photo.jpg\"$nl" +
                    "Content-Type: image/jpeg$nl$nl").toByteArray()
            )
            write(bytes)
            write("$nl--$boundary--$nl".toByteArray())
        }.toByteArray()

        val conn = open("$baseUrl/api/photos/upload", "POST", token).apply {
            doOutput = true
            readTimeout = 60_000
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        }
        try {
            conn.outputStream.use { it.write(body) }
            val text = readOrThrow(conn)
            JSONObject(text).getLong("id")
        } finally {
            conn.disconnect()
        }
    }

    /** Download a progress photo's bytes by its server id. */
    suspend fun downloadPhoto(baseUrl: String, token: String, photoId: Long): ByteArray =
        withContext(Dispatchers.IO) {
            val conn = open("$baseUrl/api/photos/file/$photoId", "GET", token).apply {
                readTimeout = 60_000
            }
            try {
                val code = conn.responseCode
                if (code !in 200..299) {
                    val text = conn.errorStream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
                    throw ServerException(code, "Photo download $code: $text")
                }
                conn.inputStream.use { it.readBytes() }
            } finally {
                conn.disconnect()
            }
        }

    /** Soft-delete a progress photo on the server; a missing photo (404) is treated as gone. */
    suspend fun deletePhoto(baseUrl: String, token: String, photoId: Long) =
        withContext(Dispatchers.IO) {
            val conn = open("$baseUrl/api/photos/$photoId", "DELETE", token)
            try {
                val code = conn.responseCode
                if (code !in 200..299 && code != 404) {
                    val text = conn.errorStream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
                    throw ServerException(code, "Photo delete $code: $text")
                }
            } finally {
                conn.disconnect()
            }
        }

    // ── HTTP plumbing ─────────────────────────────────────────────────────────────

    private fun open(urlStr: String, method: String, token: String): HttpURLConnection =
        (URL(urlStr).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 20_000
            readTimeout = 30_000
            if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Accept", "application/json")
        }

    private fun readOrThrow(conn: HttpURLConnection): String {
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
        if (code !in 200..299) throw ServerException(code, "Server $code: $text")
        return text
    }

    private fun requestJson(urlStr: String, method: String, token: String, body: JSONObject?): JSONObject {
        val conn = open(urlStr, method, token).apply {
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) {
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val text = readOrThrow(conn)
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            conn.disconnect()
        }
    }
}
