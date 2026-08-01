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
    fun record(context: Context, game: String, startMs: Long, endMs: Long, key: String): Boolean {
        if (game.isBlank() || key.isBlank()) return false
        if (!OfflineSessionLogic.isValidInterval(startMs, endMs)) return false
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        val saved = synchronized(lock) {
            val arr = OfflineSessionLogic.boundedAppend(
                readArr(prefs),
                JSONObject().put("key", key).put("game", game)
                    .put("start", startMs).put("end", endMs))
            // Called from the monitor/worker IO coroutine. Commit before scheduling the
            // worker so an immediate process death cannot lose the supposedly durable row.
            prefs.edit().putString(KEY, arr.toString()).commit()
        }
        if (!saved) return false
        // The service loop is the low-latency path; WorkManager is the durable path
        // when the process dies before connectivity returns.
        ChatFlushWorker.schedule(context)
        return true
    }

    /** Discard buffered offline sessions — see ChatUploadQueue.clear (consent withdrawn). */
    @android.annotation.SuppressLint("ApplySharedPref")
    fun clear(context: Context) {
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) { prefs.edit().remove(KEY).commit() }
    }

    fun pendingCount(context: Context): Int {
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) { return readArr(prefs).length() }
    }

    /** Deliver everything pending. No-op when empty or already flushing; stops at the
     *  first transient failure (still offline / server struggling), leaving the rest. */
    suspend fun flush(context: Context) {
        synchronized(lock) {
            if (flushing) return
            flushing = true
        }
        try {
            val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
            // Load the token first — in a WorkManager-woken process no PrefsManager ran,
            // so ApiClient.authToken would be null and every post 401 (now transient).
            ApiClient.restorePersistedToken(
                prefs.getString(Constants.KEY_AUTH_TOKEN, null),
                prefs.getString(Constants.KEY_AUTH_SERVER_URL, null)
                    ?: prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
            )
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
                        // Epoch millis preserve the instant across device/server
                        // timezones. Naive phone-local ISO strings shifted non-IST users.
                        "start_time_ms" to o.getLong("start"),
                        "end_time_ms" to o.getLong("end"),
                        "client_key" to o.getString("key")))
                    if (ChatQueueLogic.isTransientFailure(resp.code())) break   // keep, retry later
                    removeEntry(prefs, o.getString("key"))                      // 2xx / permanent 4xx → done
                } catch (_: Exception) {
                    break                                                      // network failure — keep
                }
            }
        } finally {
            synchronized(lock) { flushing = false }
        }
    }

    private fun removeEntry(prefs: SharedPreferences, key: String) = synchronized(lock) {
        val kept = OfflineSessionLogic.removeByKey(readArr(prefs), key)
        prefs.edit().putString(KEY, kept.toString()).commit()
    }
}
