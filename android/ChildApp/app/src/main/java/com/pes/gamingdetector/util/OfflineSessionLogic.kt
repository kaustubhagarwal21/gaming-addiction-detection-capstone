package com.pes.gamingdetector.util

import org.json.JSONArray
import org.json.JSONObject

/**
 * Pure decision rules for the offline-session backfill buffer, kept free of Android
 * types so they run under plain-JVM unit tests. A session START needs the server to
 * allocate an id, so a game begun with no connectivity is not tracked live; when
 * connectivity returns the child app posts the buffered {game, start, end, key} to
 * /api/session/backfill. OfflineSessionBuffer owns storage/IO; every "what happens to
 * a buffered session" rule lives here. Retry/drop reuses [ChatQueueLogic].
 */
object OfflineSessionLogic {
    const val MAX_ENTRIES = 50
    // A session is worth back-filling for a week (unlike a chat line's 24h) — the
    // server clamps its duration, so a stale-but-real session is still useful history.
    const val MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000

    /** A buffered session is usable only if its interval is sane: end at/after start,
     *  and a positive, non-absurd duration (the server clamps the ceiling too). */
    fun isValidInterval(startMs: Long, endMs: Long): Boolean =
        startMs > 0L && endMs >= startMs && (endMs - startMs) in 1_000..(MAX_AGE_MS)

    /** Drop a buffered session whose START is older than [MAX_AGE_MS]. */
    fun isStale(startMs: Long, now: Long): Boolean = now - startMs > MAX_AGE_MS

    /** A start failed before the server could allocate a usable session id. Auth and
     *  validation errors need user/action fixes; only timeout, throttling and 5xx are
     *  reasonable evidence of a temporarily unreachable backend. */
    fun isTransientStartFailure(code: Int): Boolean =
        code == 408 || code == 429 || code in 500..599

    /** Close a marker at the last time the game was definitely observed, allowing one
     *  poll interval for the transition. This prevents a marker restored hours after a
     *  process death from counting the entire stopped/offline gap as play time. */
    fun boundedEnd(startMs: Long, lastSeenMs: Long, nowMs: Long, pollMs: Long): Long {
        val observed = maxOf(startMs, lastSeenMs)
        return minOf(nowMs, observed + maxOf(0L, pollMs))
    }

    /** Append [entry], evicting oldest-first past [MAX_ENTRIES]. Mutates and returns [arr]. */
    fun boundedAppend(arr: JSONArray, entry: JSONObject): JSONArray {
        arr.put(entry)
        while (arr.length() > MAX_ENTRIES) arr.remove(0)
        return arr
    }

    /** Remove the first entry whose client key matches [key]; returns the kept entries.
     *  Entries added during a flush (a different key) are preserved. */
    fun removeByKey(cur: JSONArray, key: String): JSONArray {
        val kept = JSONArray()
        var removed = false
        for (i in 0 until cur.length()) {
            val o = cur.getJSONObject(i)
            if (!removed && o.optString("key") == key) removed = true
            else kept.put(o)
        }
        return kept
    }
}
