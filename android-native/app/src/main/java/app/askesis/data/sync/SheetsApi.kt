package app.askesis.data.sync

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Thin client over the Google Sheets v4 REST API using a Bearer access token.
 *
 * Deliberately dependency-free (HttpURLConnection + org.json) to avoid the heavyweight
 * google-api-services client and its packaging conflicts on Android.
 */
class SheetsApi {

    class SheetsException(val code: Int, message: String) : Exception(message)

    private fun base(spreadsheetId: String) =
        "https://sheets.googleapis.com/v4/spreadsheets/$spreadsheetId"

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    /** Titles of every tab in the spreadsheet. */
    suspend fun sheetTitles(spreadsheetId: String, token: String): Set<String> =
        withContext(Dispatchers.IO) {
            val json = request(
                "${base(spreadsheetId)}?fields=${enc("sheets.properties.title")}",
                "GET", token, null
            )
            val titles = mutableSetOf<String>()
            val sheets = json.optJSONArray("sheets") ?: return@withContext titles
            for (i in 0 until sheets.length()) {
                sheets.getJSONObject(i).optJSONObject("properties")
                    ?.optString("title")?.let { titles.add(it) }
            }
            titles
        }

    /** Create [title] as a new tab if it does not already exist. */
    suspend fun ensureSheet(spreadsheetId: String, token: String, title: String) {
        if (sheetTitles(spreadsheetId, token).contains(title)) return
        withContext(Dispatchers.IO) {
            val body = JSONObject().put(
                "requests",
                JSONArray().put(
                    JSONObject().put(
                        "addSheet",
                        JSONObject().put(
                            "properties", JSONObject().put("title", title)
                        )
                    )
                )
            )
            request("${base(spreadsheetId)}:batchUpdate", "POST", token, body)
        }
    }

    /** Read a range as a matrix of strings. Missing/empty cells become "". */
    suspend fun readValues(spreadsheetId: String, token: String, range: String): List<List<String>> =
        withContext(Dispatchers.IO) {
            val json = request(
                "${base(spreadsheetId)}/values/${enc(range)}",
                "GET", token, null
            )
            val values = json.optJSONArray("values") ?: return@withContext emptyList()
            (0 until values.length()).map { r ->
                val row = values.getJSONArray(r)
                (0 until row.length()).map { c -> row.optString(c, "") }
            }
        }

    suspend fun clearValues(spreadsheetId: String, token: String, range: String) {
        withContext(Dispatchers.IO) {
            request("${base(spreadsheetId)}/values/${enc(range)}:clear", "POST", token, JSONObject())
        }
    }

    /** Overwrite [range] (anchor cell, e.g. "Tab!A1") with [values] using RAW input. */
    suspend fun updateValues(
        spreadsheetId: String,
        token: String,
        range: String,
        values: List<List<String>>,
    ) {
        withContext(Dispatchers.IO) {
            val matrix = JSONArray()
            for (row in values) {
                val arr = JSONArray()
                for (cell in row) arr.put(cell)
                matrix.put(arr)
            }
            val body = JSONObject()
                .put("range", range)
                .put("majorDimension", "ROWS")
                .put("values", matrix)
            request(
                "${base(spreadsheetId)}/values/${enc(range)}?valueInputOption=RAW",
                "PUT", token, body
            )
        }
    }

    private fun request(urlStr: String, method: String, token: String, body: JSONObject?): JSONObject {
        val conn = (URL(urlStr).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 20_000
            readTimeout = 30_000
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) {
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
            if (code !in 200..299) {
                throw SheetsException(code, "Sheets API $code: $text")
            }
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            conn.disconnect()
        }
    }
}
