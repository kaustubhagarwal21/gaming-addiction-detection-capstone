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
 * Semantics: a line is queued ONLY when the server didn't save it — a network failure,
 * a 5xx, or a transient 408/429 (timeout / rate-limited). A 2xx (saved) or a permanent
 * 4xx (e.g. a closed session) drops the line, which keeps retries from piling up.
 *
 * Durability: a line is removed from disk ONLY after the server confirms it (2xx, a
 * permanent 4xx, or stale-expiry) — never before the network call. So a process death
 * mid-flush loses NOTHING; at worst a just-delivered line is re-sent on the next flush
 * and the server's de-dupe drops it. (Removal is per-line, right after each confirm, so
 * the re-send window stays inside the server's short de-dupe window.) This replaces the
 * old "clear the queue up front, merge failures back at the end" scheme, where a kill
 * between the clear and the merge-back wiped the in-flight lines.
 *
 * Concurrency: enqueue (capture threads) and flush (the monitor's poll loop) both
 * read-modify-write the same prefs key; all such access is under [lock], held only for
 * the quick prefs edit, never across the network I/O. A line enqueued during a flush has
 * a fresh id the flush never touches, so it can't be clobbered.
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
                    .put("id", java.util.UUID.randomUUID().toString())  // stable handle for removal
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
     *  flush is already running, and it stops at the first network/5xx/transient failure
     *  (still offline) leaving the rest queued in order. */
    suspend fun flush(context: android.content.Context) {
        if (flushing) return
        flushing = true
        try {
            val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
            // Read-only snapshot — the queue stays on disk; entries are removed one by one
            // only after the server confirms them (below), so a kill mid-flush loses nothing.
            val snapshot = synchronized(lock) {
                val a = readArr(prefs)
                if (a.length() == 0) return
                a
            }
            val serverUrl = prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
                ?: Constants.BASE_URL
            val api = ApiClient.getInstance(serverUrl)
            val now = System.currentTimeMillis()
            for (i in 0 until snapshot.length()) {
                val o = snapshot.getJSONObject(i)
                if (now - o.optLong("ts") > MAX_AGE_MS) {     // stale — drop without sending
                    removeEntry(prefs, o)
                    continue
                }
                try {
                    val resp = api.uploadChat(
                        o.getInt("sid"),
                        mapOf("message" to o.getString("msg"),
                              "source" to o.optString("src", "keyboard"))
                    )
                    val code = resp.code()
                    // Keep on a server error (5xx) or a transient client error (408 timeout,
                    // 429 rate-limited) — the line wasn't saved. Stop the pass so we don't
                    // hammer a struggling/throttling server and so order is preserved. Any
                    // other 4xx is a permanent reject (e.g. closed session) → drop it.
                    if (code in 500..599 || code == 408 || code == 429) break
                    removeEntry(prefs, o)                     // 2xx saved, or 4xx permanent → done
                } catch (_: Exception) {
                    break                                     // network failure — keep this + the rest
                }
            }
        } finally {
            flushing = false
        }
    }

    /** Remove exactly one queued entry from disk (matched by its id, falling back to full
     *  content for legacy entries written before ids existed). Re-reads under the lock so
     *  lines enqueued during the flush are preserved. */
    private fun removeEntry(prefs: SharedPreferences, target: JSONObject) = synchronized(lock) {
        val cur  = readArr(prefs)
        val tid  = target.optString("id")
        val kept = JSONArray()
        var removed = false
        for (i in 0 until cur.length()) {
            val o = cur.getJSONObject(i)
            val match = if (tid.isNotEmpty()) o.optString("id") == tid
                        else o.toString() == target.toString()
            if (match && !removed) removed = true            // skip the first match (drop it)
            else kept.put(o)
        }
        prefs.edit().putString(KEY, kept.toString()).apply()
    }
}
