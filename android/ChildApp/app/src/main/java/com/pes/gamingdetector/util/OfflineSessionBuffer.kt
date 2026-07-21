package com.pes.gamingdetector.util

import android.content.Context
import android.content.SharedPreferences
import com.pes.gamingdetector.api.ApiClient
import org.json.JSONArray
import org.json.JSONObject

/**
 * Disk-backed buffer of sessions that ran while OFFLINE. A session start needs the
 * server, so a game begun with no connectivity is not tracked live (the paper's
 * "session started while offline" gap). PassiveMonitorService records the offline
 * start; when it later confirms the game online (connectivity returned) it hands the
 * completed interval here, and this buffer posts it to /api/session/backfill — reliably,
 * surviving process death — so the offline head becomes a real, scored, parent-visible
 * session instead of being lost.
 *
 * Durability mirrors ChatUploadQueue: confirm-then-delete (an entry leaves disk only
 * after the server saves or permanently rejects it) and a stable per-entry key that the
 * server de-dupes on, so a kill mid-flush loses nothing and a re-send can't duplicate.
 * Decision rules live in [OfflineSessionLogic].
 */
object OfflineSessionBuffer {
    private const val KEY = "pending_offline_sessions"
    private val lock = Any()
    @Volatile private var flushing = false

    private fun readArr(prefs: SharedPreferences): JSONArray =
        try { JSONArray(prefs.getString(KEY, "[]")) } catch (_: Exception) { JSONArray() }

    /** Buffer one completed offline session for backfill. Invalid intervals are ignored. */
    fun record(context: Context, game: String, startMs: Long, endMs: Long, key: String) {
        if (game.isBlank() || key.isBlank()) return
        if (!OfflineSessionLogic.isValidInterval(startMs, endMs)) return
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) {
            val arr = OfflineSessionLogic.boundedAppend(
                readArr(prefs),
                JSONObject().put("key", key).put("game", game)
                    .put("start", startMs).put("end", endMs))
            prefs.edit().putString(KEY, arr.toString()).apply()
        }
    }

    fun pendingCount(context: Context): Int {
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) { return readArr(prefs).length() }
    }

    /** Deliver everything pending. No-op when empty or already flushing; stops at the
     *  first transient failure (still offline / server struggling), leaving the rest. */
    suspend fun flush(context: Context) {
        if (flushing) return
        flushing = true
        try {
            val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
            // Load the token first — in a WorkManager-woken process no PrefsManager ran,
            // so ApiClient.authToken would be null and every post 401 (now transient).
            ApiClient.authToken = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
            val userId = prefs.getInt(Constants.KEY_USER_ID, -1)
            if (userId == -1) return
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
                if (OfflineSessionLogic.isStale(o.optLong("start"), now)) {
                    removeEntry(prefs, o.getString("key")); continue
                }
                try {
                    val resp = api.backfillSession(mapOf(
                        "user_id" to userId,
                        "game_name" to o.getString("game"),
                        "start_time" to isoUtc(o.getLong("start")),
                        "end_time" to isoUtc(o.getLong("end")),
                        "client_key" to o.getString("key")))
                    if (ChatQueueLogic.isTransientFailure(resp.code())) break   // keep, retry later
                    removeEntry(prefs, o.getString("key"))                      // 2xx / permanent 4xx → done
                } catch (_: Exception) {
                    break                                                      // network failure — keep
                }
            }
        } finally {
            flushing = false
        }
    }

    /** Epoch millis → server-parseable local ISO ('yyyy-MM-ddTHH:mm:ss'). The backend
     *  reads times in its own (IST) clock; a naive local timestamp matches how live
     *  sessions are stored, so a back-filled session sits correctly among them. */
    private fun isoUtc(ms: Long): String {
        val fmt = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
        return fmt.format(java.util.Date(ms))
    }

    private fun removeEntry(prefs: SharedPreferences, key: String) = synchronized(lock) {
        val kept = OfflineSessionLogic.removeByKey(readArr(prefs), key)
        prefs.edit().putString(KEY, kept.toString()).apply()
    }
}
