package com.pes.gamingdetector.util

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Offline-session backfill rules: the guarantees behind "a session played offline is
 * recorded once when connectivity returns, or deliberately dropped — never duplicated
 * and never absurd".
 */
class OfflineSessionLogicTest {

    private fun entry(key: String, start: Long = 1_000_000L, end: Long = 1_003_600_000L) =
        JSONObject().put("key", key).put("game", "BGMI").put("start", start).put("end", end)

    @Test
    fun `valid interval requires end at-or-after start and a sane duration`() {
        assertTrue(OfflineSessionLogic.isValidInterval(1_000L, 1_000L + 3_600_000L))
        assertFalse(OfflineSessionLogic.isValidInterval(0L, 3_600_000L))          // no start
        assertFalse(OfflineSessionLogic.isValidInterval(5_000L, 4_000L))          // end before start
        assertFalse(OfflineSessionLogic.isValidInterval(1_000L, 1_000L))          // zero duration
        assertFalse(OfflineSessionLogic.isValidInterval(
            1_000L, 1_000L + OfflineSessionLogic.MAX_AGE_MS + 1))                 // absurdly long
    }

    @Test
    fun `stale sessions are dropped after a week`() {
        val now = 10_000_000_000L
        assertFalse(OfflineSessionLogic.isStale(now - OfflineSessionLogic.MAX_AGE_MS, now))
        assertTrue(OfflineSessionLogic.isStale(now - OfflineSessionLogic.MAX_AGE_MS - 1, now))
    }

    @Test
    fun `only retryable start responses create an offline marker`() {
        assertTrue(OfflineSessionLogic.isTransientStartFailure(408))
        assertTrue(OfflineSessionLogic.isTransientStartFailure(429))
        assertTrue(OfflineSessionLogic.isTransientStartFailure(503))
        assertFalse(OfflineSessionLogic.isTransientStartFailure(400))
        assertFalse(OfflineSessionLogic.isTransientStartFailure(401))
        assertFalse(OfflineSessionLogic.isTransientStartFailure(404))
    }

    @Test
    fun `restored marker end is capped near its last foreground observation`() {
        val start = 1_000L
        val lastSeen = 31_000L
        assertEquals(36_000L,
            OfflineSessionLogic.boundedEnd(start, lastSeen, 3_600_000L, 5_000L))
        assertEquals(33_000L,
            OfflineSessionLogic.boundedEnd(start, lastSeen, 33_000L, 5_000L))
    }

    @Test
    fun `buffer is bounded oldest-first`() {
        val arr = JSONArray()
        for (i in 0 until OfflineSessionLogic.MAX_ENTRIES + 2)
            OfflineSessionLogic.boundedAppend(arr, entry("k$i"))
        assertEquals(OfflineSessionLogic.MAX_ENTRIES, arr.length())
        assertEquals("k2", arr.getJSONObject(0).getString("key"))   // k0,k1 evicted
    }

    @Test
    fun `removeByKey removes exactly the confirmed session and keeps the rest`() {
        var arr = JSONArray().put(entry("a")).put(entry("b")).put(entry("c"))
        arr = OfflineSessionLogic.removeByKey(arr, "b")
        assertEquals(2, arr.length())
        assertEquals("a", arr.getJSONObject(0).getString("key"))
        assertEquals("c", arr.getJSONObject(1).getString("key"))
    }

    @Test
    fun `removeByKey on an absent key is a no-op`() {
        var arr = JSONArray().put(entry("a"))
        arr = OfflineSessionLogic.removeByKey(arr, "zzz")
        assertEquals(1, arr.length())
    }
}
