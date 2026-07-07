package app.askesis.data.sync

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * Thin client over the Google Drive v3 REST API using a Bearer access token.
 *
 * Like [SheetsApi], deliberately dependency-free (HttpURLConnection + org.json) to avoid
 * the heavyweight google-api-services client. Only the handful of operations the photo
 * feature needs: multipart create, media download, and delete. The app uses the
 * `drive.file` scope, so it can only see files it created — exactly the progress photos.
 */
class DriveApi {

    class DriveException(val code: Int, message: String) : Exception(message)

    /**
     * Upload [bytes] as a new Drive file via a multipart/related request and return its
     * file id. [name] is the Drive filename; [mimeType] defaults to JPEG.
     */
    suspend fun uploadFile(
        token: String,
        name: String,
        bytes: ByteArray,
        mimeType: String = "image/jpeg",
    ): String = withContext(Dispatchers.IO) {
        val boundary = "askesisBoundary" + bytes.size + name.hashCode()
        val metadata = JSONObject().put("name", name).toString()

        val body = ByteArrayOutputStream().apply {
            write("--$boundary\r\n".toByteArray())
            write("Content-Type: application/json; charset=UTF-8\r\n\r\n".toByteArray())
            write(metadata.toByteArray())
            write("\r\n--$boundary\r\n".toByteArray())
            write("Content-Type: $mimeType\r\n\r\n".toByteArray())
            write(bytes)
            write("\r\n--$boundary--\r\n".toByteArray())
        }.toByteArray()

        val conn = (URL("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart")
            .openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 20_000
            readTimeout = 60_000
            doOutput = true
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Content-Type", "multipart/related; boundary=$boundary")
        }
        try {
            conn.outputStream.use { it.write(body) }
            val code = conn.responseCode
            val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
            if (code !in 200..299) throw DriveException(code, "Drive upload $code: $text")
            JSONObject(text).getString("id")
        } finally {
            conn.disconnect()
        }
    }

    /** Download the raw bytes of a Drive file by id. */
    suspend fun downloadFile(token: String, fileId: String): ByteArray = withContext(Dispatchers.IO) {
        val conn = (URL("https://www.googleapis.com/drive/v3/files/$fileId?alt=media")
            .openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 20_000
            readTimeout = 60_000
            setRequestProperty("Authorization", "Bearer $token")
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299) {
                val text = conn.errorStream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
                throw DriveException(code, "Drive download $code: $text")
            }
            conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    /** Best-effort delete; a missing file (404) is treated as already gone. */
    suspend fun deleteFile(token: String, fileId: String) = withContext(Dispatchers.IO) {
        val conn = (URL("https://www.googleapis.com/drive/v3/files/$fileId")
            .openConnection() as HttpURLConnection).apply {
            requestMethod = "DELETE"
            connectTimeout = 20_000
            readTimeout = 30_000
            setRequestProperty("Authorization", "Bearer $token")
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299 && code != 404) {
                val text = conn.errorStream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
                throw DriveException(code, "Drive delete $code: $text")
            }
        } finally {
            conn.disconnect()
        }
    }
}
