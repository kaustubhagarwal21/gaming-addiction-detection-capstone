package com.pes.gamingdetector.util

import android.content.Context
import com.pes.gamingdetector.api.ApiClient
import org.json.JSONArray
import org.json.JSONObject

/**
 * Tiny disk-backed retry queue for chat lines whose upload failed (device offline,
 * cloud cold-start). Previously those lines were silently lost — the one capture gap
 * the server's stale-session self-healing couldn't cover. Captured text is small and
 * rare, so a bounded JSON array in the encrypted prefs is plenty; no database needed.
 *
 * Semantics: a line is queued ONLY on a network failure (the request never reached the
 * server). HTTP-level rejections are not retried — the server saw the line and refused
 * it — which keeps retries from creating duplicates beyond the server's own 8-second
 * de-dupe window.
 */
object ChatUploadQueue {
    private const val KEY = "pending_chat_queue"
    private const val MAX_LINES = 50
    private const val MAX_AGE_MS = 24 * 60 * 60 * 1000L   // a day-old line is stale — drop

    @Volatile private var flushing = false

    @Synchronized
    fun enqueue(context: Context, sessionId: Int, message: String, source: String) {
        if (sessionId == -1 || message.isBlank()) return
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        val arr = try { JSONArray(prefs.getString(KEY, "[]")) } catch (_: Exception) { JSONArray() }
        arr.put(
            JSONObject()
                .put("sid", sessionId)
                .put("msg", message)
                .put("src", source)
                .put("ts", System.currentTimeMillis())
        )
        while (arr.length() > MAX_LINES) arr.remove(0)   // bounded: drop oldest
        prefs.edit().putString(KEY, arr.toString()).apply()
    }

    /** Try to deliver everything pending. Cheap to call often: no-op when empty or a
     *  flush is already running, and it stops at the first network failure (still
     *  offline) keeping the rest queued in order. */
    suspend fun flush(context: Context) {
        if (flushing) return
        flushing = true
        try {
            val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
            val raw = prefs.getString(KEY, null) ?: return
            val arr = try { JSONArray(raw) } catch (_: Exception) { JSONArray() }
            if (arr.length() == 0) return
            val serverUrl = prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
                ?: Constants.BASE_URL
            val api = ApiClient.getInstance(serverUrl)
            val now = System.currentTimeMillis()
            val remaining = JSONArray()
            var offline = false
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                if (offline) { remaining.put(o); continue }
                if (now - o.optLong("ts") > MAX_AGE_MS) continue   // stale — drop
                try {
                    val resp = api.uploadChat(
                        o.getInt("sid"),
                        mapOf("message" to o.getString("msg"),
                              "source" to o.optString("src", "keyboard"))
                    )
                    // Keep on a SERVER error (5xx) — the line wasn't saved, so retry it
                    // later rather than silently dropping it. A 2xx means saved; a 4xx
                    // (e.g. bad/closed session) will never succeed, so drop it. Stop the
                    // pass on a 5xx so we don't hammer a struggling server.
                    if (resp.code() >= 500) { offline = true; remaining.put(o) }
                    // else (2xx/4xx): delivered or permanently rejected — drop from queue.
                } catch (_: Exception) {
                    offline = true              // network failure — keep this + the rest
                    remaining.put(o)
                }
            }
            prefs.edit().putString(KEY, remaining.toString()).apply()
        } finally {
            flushing = false
        }
    }
}
