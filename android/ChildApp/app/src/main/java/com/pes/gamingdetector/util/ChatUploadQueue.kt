package com.pes.gamingdetector.util

import android.content.SharedPreferences
import com.pes.gamingdetector.api.ApiClient
import org.json.JSONArray
import org.json.JSONObject

/**
 * Tiny disk-backed retry queue for chat lines whose upload failed (device offline,
 * cloud cold-start). Previously those lines were silently lost — the one capture gap
 * the server's stale-session self-healing couldn't cover. Captured text is small and
 * rare, so a bounded JSON array in the encrypted prefs is plenty; no database needed.
 *
 * Semantics: a line is queued ONLY on a network failure or a server (5xx) error — the
 * request never reached, or the server didn't save it. A 2xx (saved) or a 4xx
 * (permanently rejected, e.g. a closed session) drops the line, which keeps retries
 * from creating duplicates beyond the server's own de-dupe window.
 *
 * Concurrency: enqueue (capture threads) and flush (the monitor's poll loop) both
 * read-modify-write the same prefs key. All prefs access is under [lock]; flush does
 * its slow network I/O OUTSIDE the lock by snapshotting-and-clearing the queue first,
 * then merging failures back together with anything enqueued meanwhile — so a line
 * captured during a flush can never be overwritten and lost.
 */
object ChatUploadQueue {
    private const val KEY = "pending_chat_queue"
    private const val MAX_LINES = 50
    private const val MAX_AGE_MS = 24 * 60 * 60 * 1000L   // a day-old line is stale — drop

    private val lock = Any()
    @Volatile private var flushing = false

    private fun readArr(prefs: SharedPreferences): JSONArray =
        try { JSONArray(prefs.getString(KEY, "[]")) } catch (_: Exception) { JSONArray() }

    fun enqueue(context: android.content.Context, sessionId: Int, message: String, source: String) {
        if (sessionId == -1 || message.isBlank()) return
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) {
            val arr = readArr(prefs)
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
    }

    /** Try to deliver everything pending. Cheap to call often: no-op when empty or a
     *  flush is already running, and it stops at the first network/5xx failure (still
     *  offline) keeping the rest queued in order. */
    suspend fun flush(context: android.content.Context) {
        if (flushing) return
        flushing = true
        try {
            val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
            // Take ownership: snapshot the queue and clear it atomically, so any line
            // enqueued DURING the network loop below lands in a fresh list rather than
            // being clobbered when we write failures back.
            val snapshot = synchronized(lock) {
                val a = readArr(prefs)
                if (a.length() == 0) return
                prefs.edit().putString(KEY, "[]").apply()
                a
            }
            val serverUrl = prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
                ?: Constants.BASE_URL
            val api = ApiClient.getInstance(serverUrl)
            val now = System.currentTimeMillis()
            val remaining = JSONArray()
            var offline = false
            for (i in 0 until snapshot.length()) {
                val o = snapshot.getJSONObject(i)
                if (offline) { remaining.put(o); continue }
                if (now - o.optLong("ts") > MAX_AGE_MS) continue   // stale — drop
                try {
                    val resp = api.uploadChat(
                        o.getInt("sid"),
                        mapOf("message" to o.getString("msg"),
                              "source" to o.optString("src", "keyboard"))
                    )
                    // Keep on a SERVER error (5xx) — the line wasn't saved. 2xx = saved;
                    // 4xx = permanently rejected (e.g. closed session). Stop the pass on
                    // a 5xx so we don't hammer a struggling server.
                    if (resp.code() >= 500) { offline = true; remaining.put(o) }
                } catch (_: Exception) {
                    offline = true              // network failure — keep this + the rest
                    remaining.put(o)
                }
            }
            // Merge undelivered lines back AHEAD of anything enqueued during the flush
            // (preserves rough order), under the lock, then re-bound.
            if (remaining.length() > 0) synchronized(lock) {
                val current = readArr(prefs)            // lines enqueued during the flush
                val merged = JSONArray()
                for (i in 0 until remaining.length()) merged.put(remaining.get(i))
                for (i in 0 until current.length())   merged.put(current.get(i))
                while (merged.length() > MAX_LINES) merged.remove(0)
                prefs.edit().putString(KEY, merged.toString()).apply()
            }
        } finally {
            flushing = false
        }
    }
}
