package com.pes.gamingdetector.util

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The offline chat queue's decision rules. These semantics are what guarantee
 * "a captured line is either delivered or deliberately dropped, never silently lost"
 * — a regression here loses chat evidence without any visible failure.
 */
class ChatQueueLogicTest {

    private fun entry(id: String?, msg: String = "gg", sid: Int = 1, ts: Long = 0L): JSONObject {
        val o = JSONObject().put("sid", sid).put("msg", msg).put("src", "keyboard").put("ts", ts)
        if (id != null) o.put("id", id)
        return o
    }

    // ── retry vs drop ───────────────────────────────────────────────────────

    @Test
    fun `5xx and transient 4xx keep the line for retry`() {
        // 401 is transient: in the WorkManager path the token may not be loaded yet, so a
        // 401 must re-queue (not drop) — the line survives until the token is present or
        // the 24h stale-drop fires.
        for (code in listOf(500, 502, 503, 599, 408, 429, 401)) {
            assertTrue("expected retry for $code", ChatQueueLogic.isTransientFailure(code))
        }
    }

    @Test
    fun `2xx and permanent 4xx drop the line`() {
        for (code in listOf(200, 201, 204, 400, 403, 404, 410, 422)) {
            assertFalse("expected drop for $code", ChatQueueLogic.isTransientFailure(code))
        }
    }

    // ── staleness ───────────────────────────────────────────────────────────

    @Test
    fun `line exactly at max age is still sent, one ms past is dropped`() {
        val now = 1_000_000_000L
        assertFalse(ChatQueueLogic.isStale(now - ChatQueueLogic.MAX_AGE_MS, now))
        assertTrue(ChatQueueLogic.isStale(now - ChatQueueLogic.MAX_AGE_MS - 1, now))
    }

    // ── bounded append ──────────────────────────────────────────────────────

    @Test
    fun `queue is bounded and evicts oldest first`() {
        val arr = JSONArray()
        for (i in 0 until ChatQueueLogic.MAX_LINES + 3) {
            ChatQueueLogic.boundedAppend(arr, entry("id$i", msg = "m$i"))
        }
        assertEquals(ChatQueueLogic.MAX_LINES, arr.length())
        // 0..2 evicted; the survivors start at 3 and keep insertion order
        assertEquals("m3", arr.getJSONObject(0).getString("msg"))
        assertEquals("m${ChatQueueLogic.MAX_LINES + 2}",
            arr.getJSONObject(arr.length() - 1).getString("msg"))
    }

    // ── removal (per-line confirm during flush) ─────────────────────────────

    @Test
    fun `removes exactly the confirmed line by id`() {
        var arr = JSONArray().put(entry("a")).put(entry("b")).put(entry("c"))
        arr = ChatQueueLogic.removeFirstMatch(arr, entry("b"))
        assertEquals(2, arr.length())
        assertEquals("a", arr.getJSONObject(0).getString("id"))
        assertEquals("c", arr.getJSONObject(1).getString("id"))
    }

    @Test
    fun `identical texts with different ids are distinct lines - only the confirmed one is removed`() {
        // The user typing the same message twice must not collapse to one queued line.
        var arr = JSONArray().put(entry("a", msg = "same")).put(entry("b", msg = "same"))
        arr = ChatQueueLogic.removeFirstMatch(arr, entry("a", msg = "same"))
        assertEquals(1, arr.length())
        assertEquals("b", arr.getJSONObject(0).getString("id"))
    }

    @Test
    fun `legacy entries without ids fall back to content matching and remove only the first duplicate`() {
        var arr = JSONArray().put(entry(null, msg = "dup")).put(entry(null, msg = "dup"))
        arr = ChatQueueLogic.removeFirstMatch(arr, entry(null, msg = "dup"))
        assertEquals(1, arr.length())
    }

    @Test
    fun `removing an absent entry leaves the queue untouched`() {
        var arr = JSONArray().put(entry("a"))
        arr = ChatQueueLogic.removeFirstMatch(arr, entry("zzz"))
        assertEquals(1, arr.length())
        assertEquals("a", arr.getJSONObject(0).getString("id"))
    }

    @Test
    fun `lines enqueued during a flush survive the confirm of a snapshotted line`() {
        // flush snapshots [a]; while a is in-flight, d is enqueued; confirming a must keep d
        var disk = JSONArray().put(entry("a")).put(entry("d", msg = "typed mid-flush"))
        disk = ChatQueueLogic.removeFirstMatch(disk, entry("a"))
        assertEquals(1, disk.length())
        assertEquals("d", disk.getJSONObject(0).getString("id"))
    }
}
