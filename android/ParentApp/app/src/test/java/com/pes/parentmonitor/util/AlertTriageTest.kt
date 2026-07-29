package com.pes.parentmonitor.util

import com.pes.parentmonitor.api.Alert
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The alert-notification decision rules. A past bug lives here as a regression test:
 * the shared high-water mark that suppressed a sibling's alerts.
 */
class AlertTriageTest {

    private fun alert(id: Int, severity: String = "medium", read: Boolean = false) =
        Alert(id = id, type = "toxicity", message = "m$id", severity = severity,
              createdAt = "2026-07-06 00:00:00", ageMinutes = 0, read = read)

    // ── which alerts are new ────────────────────────────────────────────────

    @Test
    fun `only unread alerts above the high-water mark count, oldest first`() {
        val alerts = listOf(
            alert(5),                    // at the mark — already notified
            alert(9),
            alert(7),
            alert(8, read = true),       // read in-app — never re-notify
        )
        val fresh = AlertTriage.newAlertsSince(alerts, lastNotifiedId = 5)
        assertEquals(listOf(7, 9), fresh.map { it.id })
    }

    @Test
    fun `null alert list from the api means nothing new`() {
        assertTrue(AlertTriage.newAlertsSince(null, 0).isEmpty())
    }

    @Test
    fun `per-child mark regression - a fresh child starts from zero and sees its backlog`() {
        // With the old SHARED mark, viewing child A (ids ~100) suppressed child B's
        // older-id alerts forever. Per-child marks start at 0 for B.
        val childB = listOf(alert(12), alert(13))
        assertEquals(2, AlertTriage.newAlertsSince(childB, lastNotifiedId = 0).size)
    }

    // ── which one to show ───────────────────────────────────────────────────

    @Test
    fun `worst alert wins regardless of arrival order`() {
        val picked = AlertTriage.worstOf(listOf(alert(1, "low"), alert(2, "high"), alert(3, "medium")))
        assertEquals(2, picked?.id)
    }

    @Test
    fun `unknown severities rank below low`() {
        assertTrue(AlertTriage.severityRank("low") > AlertTriage.severityRank("critical-typo"))
        val picked = AlertTriage.worstOf(listOf(alert(1, "weird"), alert(2, "low")))
        assertEquals(2, picked?.id)
    }

    @Test
    fun `notification title carries the batch count`() {
        // A burst collapses to one card (worst severity wins), so the title must say
        // how many alerts arrived — a lone card for three alerts hid the other two.
        assertEquals("Gaming alert · Arjun", AlertTriage.notificationTitle("Arjun", 1))
        assertEquals("Gaming alert · Arjun", AlertTriage.notificationTitle("Arjun", 0))
        assertEquals("3 new alerts · Arjun", AlertTriage.notificationTitle("Arjun", 3))
    }

    @Test
    fun `feedback covers every model assessment but not operational events`() {
        listOf("risk", "RISK_REVISION", "toxicity", "toxicity_streak").forEach {
            assertTrue("$it should be rateable", AlertTriage.isFeedbackEligible(it))
        }
        listOf("session_start", "login", "offline", "permission", "tamper", "").forEach {
            assertFalse("$it is factual, not a model assessment",
                AlertTriage.isFeedbackEligible(it))
        }
    }
}
