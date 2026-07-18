package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RiskPresentationTest {
    @Test
    fun `canonical machine categories use family safe labels`() {
        assertEquals("Low concern", RiskPresentation.displayLabel("casual"))
        assertEquals("Some concern", RiskPresentation.displayLabel("at_risk"))
        assertEquals("High concern", RiskPresentation.displayLabel("addicted"))
    }

    @Test
    fun `canonical server label wins and legacy raw labels stay safe`() {
        assertEquals(
            "Some concern",
            RiskPresentation.displayLabel("at_risk", "Some concern")
        )
        assertEquals(
            "Some concern",
            RiskPresentation.displayLabel("casual", "at_risk")
        )
        assertEquals("Unknown", RiskPresentation.displayLabel(null))
    }

    @Test
    fun `period describes latest daily aggregation and pluralizes sessions`() {
        assertEquals("Today \u00B7 1 session", RiskPresentation.periodText("Today", 1))
        assertEquals("Yesterday \u00B7 2 sessions", RiskPresentation.periodText("Yesterday", 2))
        assertEquals("Jun 03", RiskPresentation.periodText("Jun 03", null))
        assertNull(RiskPresentation.periodText(null, 2))
    }

    @Test
    fun `scoped session text cannot be mistaken for dashboard aggregate`() {
        assertEquals(
            "Live session: Some concern \u00B7 34%",
            RiskPresentation.scopedRiskText("Live session", "at_risk", 0.34)
        )
        assertEquals(
            "This session: Low concern \u00B7 25%",
            RiskPresentation.scopedRiskText("This session", "casual", 0.25)
        )
    }
}
