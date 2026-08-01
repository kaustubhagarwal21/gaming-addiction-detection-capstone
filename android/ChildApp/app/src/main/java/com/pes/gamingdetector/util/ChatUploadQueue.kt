package com.pes.gamingdetector.util

import android.annotation.SuppressLint
import android.content.SharedPreferences
import com.pes.gamingdetector.api.ApiClient
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean

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
    // Decision rules (bounds, staleness, retry vs drop, removal matching) live in
    // ChatQueueLogic — pure and JVM-unit-tested; this object owns storage and I/O.

    private val lock = Any()
    private val flushing = AtomicBoolean(false)

    private fun readArr(prefs: SharedPreferences): JSONArray =
        try { JSONArray(prefs.getString(KEY, "[]")) } catch (_: Exception) { JSONArray() }

    @SuppressLint("ApplySharedPref") // capture runs off-main; durability is intentional
    fun enqueue(context: android.content.Context, sessionId: Int, message: String, source: String) {
        if (sessionId == -1 || message.isBlank()) return
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) {
            val arr = ChatQueueLogic.boundedAppend(
                readArr(prefs),
                JSONObject()
                    .put("id", java.util.UUID.randomUUID().toString())  // stable handle for removal
                    .put("sid", sessionId)
                    .put("msg", message)
                    .put("src", source)
                    .put("ts", System.currentTimeMillis())
            )
            prefs.edit().putString(KEY, arr.toString()).commit()
        }
        // Durable retry: fires when connectivity returns even if the monitoring service
        // (whose poll loop is the low-latency flush path) has since been killed.
        ChatFlushWorker.schedule(context)
    }

    /** Discard everything still queued. Called when consent is withdrawn or the policy
     *  changes: permission to hold and transmit this captured text is gone, so keeping it
     *  on disk (and letting the durable worker keep retrying it) is not defensible. */
    @SuppressLint("ApplySharedPref")
    fun clear(context: android.content.Context) {
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) { prefs.edit().remove(KEY).commit() }
    }

    /** Lines still waiting on disk — lets the flush worker decide success vs retry. */
    fun pendingCount(context: android.content.Context): Int {
        val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
        synchronized(lock) { return readArr(prefs).length() }
    }

    /** Try to deliver everything pending. Cheap to call often: no-op when empty or a
     *  flush is already running, and it stops at the first network/5xx/transient failure
     *  (still offline) leaving the rest queued in order. */
    suspend fun flush(context: android.content.Context) {
        // WorkManager and PassiveMonitorService can call flush at the same instant. A
        // volatile check followed by a volatile write is not atomic; both callers could
        // upload the same snapshot. CAS gives exactly one caller ownership of the pass.
        if (!flushing.compareAndSet(false, true)) return
        try {
            val prefs = SecurePrefs.get(context, Constants.PREFS_NAME)
            // Load the bearer token into ApiClient BEFORE any upload. In the WorkManager
            // path (process was killed, then woken purely to flush) no PrefsManager was
            // constructed, so ApiClient.authToken is null → the server 401s every line and,
            // treated as a permanent 4xx, they were dropped. This is exactly the
            // process-death case this durable queue exists to cover, so it must send the
            // token itself rather than assume some Activity/Service already did.
            ApiClient.restorePersistedToken(
                prefs.getString(Constants.KEY_AUTH_TOKEN, null),
                prefs.getString(Constants.KEY_AUTH_SERVER_URL, null)
                    ?: prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
            )
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
                if (ChatQueueLogic.isStale(o.optLong("ts"), now)) {  // stale — drop without sending
                    removeEntry(prefs, o)
                    continue
                }
                try {
                    val resp = api.uploadChat(
                        o.getInt("sid"),
                        mapOf("message" to o.getString("msg"),
                              "source" to o.optString("src", "keyboard"))
                    )
                    // Keep on a server error (5xx) or a transient client error (408 timeout,
                    // 429 rate-limited) — the line wasn't saved. Stop the pass so we don't
                    // hammer a struggling/throttling server and so order is preserved. Any
                    // other 4xx is a permanent reject (e.g. closed session) → drop it.
                    if (ChatQueueLogic.isTransientFailure(resp.code())) break
                    removeEntry(prefs, o)                     // 2xx saved, or 4xx permanent → done
                } catch (_: Exception) {
                    break                                     // network failure — keep this + the rest
                }
            }
        } finally {
            flushing.set(false)
        }
    }

    /** Remove exactly one queued entry from disk (matched by its id, falling back to full
     *  content for legacy entries written before ids existed). Re-reads under the lock so
     *  lines enqueued during the flush are preserved. */
    @SuppressLint("ApplySharedPref")
    private fun removeEntry(prefs: SharedPreferences, target: JSONObject) = synchronized(lock) {
        val kept = ChatQueueLogic.removeFirstMatch(readArr(prefs), target)
        prefs.edit().putString(KEY, kept.toString()).commit()
    }
}
