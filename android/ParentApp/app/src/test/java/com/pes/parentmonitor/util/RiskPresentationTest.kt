package com.pes.parentmonitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RiskPresentationTest {
    @Test
    fun `server screening label is the display source of truth`() {
        assertEquals(
            "Some concern",
            RiskPresentation.displayLabel("at_risk", "Some concern")
        )
        assertEquals(
            "Some concern",
            RiskPresentation.displayLabel("casual", "at_risk")
        )
    }

    @Test
    fun `legacy payloads fall back to canonical friendly labels`() {
        assertEquals("Low concern", RiskPresentation.displayLabel("casual", null))
        assertEquals("Some concern", RiskPresentation.displayLabel("at_risk", null))
        assertEquals("High concern", RiskPresentation.displayLabel("addicted", null))
        assertEquals("Unknown", RiskPresentation.displayLabel(null, null))
    }

    @Test
    fun `period describes the aggregate and pluralizes sessions`() {
        assertEquals("Today · 1 session", RiskPresentation.periodText("Today", 1))
        assertEquals("Yesterday · 2 sessions", RiskPresentation.periodText("Yesterday", 2))
        assertEquals("Jun 03", RiskPresentation.periodText("Jun 03", null))
        assertNull(RiskPresentation.periodText(null, 2))
    }

    @Test
    fun `details keep score and period provenance together`() {
        assertEquals(
            "34% risk score · Yesterday · 2 sessions",
            RiskPresentation.detailText(0.34, "Yesterday", 2)
        )
        assertEquals("25% risk score", RiskPresentation.detailText(0.25, null, null))
    }
}
