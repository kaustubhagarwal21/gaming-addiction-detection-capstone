package com.pes.gamingdetector.util

import org.json.JSONArray
import org.json.JSONObject

/**
 * The pure decision logic of [ChatUploadQueue], kept free of Android types
 * (SharedPreferences, Context, Retrofit) so it runs under plain-JVM unit tests.
 * ChatUploadQueue owns storage and I/O; every rule that decides WHAT happens to a
 * queued line lives here.
 */
object ChatQueueLogic {
    const val MAX_LINES = 50
    const val MAX_AGE_MS = 24 * 60 * 60 * 1000L   // a day-old line is stale — drop

    /** True when the server did NOT save the line and a retry makes sense: any 5xx,
     *  or the transient client errors 408 (timeout) / 429 (rate-limited) / 401
     *  (unauthenticated — token not yet loaded / momentarily rotated; a genuinely dead
     *  token just re-queues until the 24h stale-drop). A 2xx means saved; any other 4xx
     *  is a permanent reject (e.g. closed session) — drop it. */
    fun isTransientFailure(code: Int): Boolean =
        code in 500..599 || code == 408 || code == 429 || code == 401

    /** A line older than [MAX_AGE_MS] is dropped without sending. */
    fun isStale(ts: Long, now: Long): Boolean = now - ts > MAX_AGE_MS

    /** Append [entry], then evict oldest-first until the queue is back under
     *  [MAX_LINES]. Mutates and returns [arr]. */
    fun boundedAppend(arr: JSONArray, entry: JSONObject): JSONArray {
        arr.put(entry)
        while (arr.length() > MAX_LINES) arr.remove(0)   // bounded: drop oldest
        return arr
    }

    /** Remove exactly one entry matching [target] (by its id, falling back to full
     *  content for legacy entries written before ids existed). Returns the kept
     *  entries as a new array; everything else — including lines enqueued after the
     *  flush snapshot was taken — is preserved in order. */
    fun removeFirstMatch(cur: JSONArray, target: JSONObject): JSONArray {
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
        return kept
    }
}
