package com.pes.parentmonitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Mirrors the other app's copy exactly (CI enforces the main-source twin too). */
class RiskPresentationTest {

    @Test
    fun `machine keys and server labels map to family-facing labels`() {
        assertEquals("Low concern", RiskPresentation.displayLabel("casual"))
        assertEquals("Some concern", RiskPresentation.displayLabel("at_risk"))
        assertEquals("High concern", RiskPresentation.displayLabel("addicted"))
        assertEquals("Some concern", RiskPresentation.displayLabel("AT-RISK"))
        assertEquals("High concern", RiskPresentation.displayLabel(null, "High concern"))
        assertEquals("Low concern", RiskPresentation.displayLabel("casual", "Some concern"))
        assertEquals("Some concern", RiskPresentation.displayLabel("at_risk", "Low concern"))
        assertEquals("Unknown", RiskPresentation.displayLabel(null, null))
        assertEquals("Unknown", RiskPresentation.displayLabel("  ", ""))
        assertEquals("Mystery", RiskPresentation.displayLabel("mystery"))
    }

    @Test
    fun `score texts round and tolerate null`() {
        assertEquals("34%", RiskPresentation.scoreText(0.336))
        assertEquals("—", RiskPresentation.scoreText(null))
        assertEquals("—", RiskPresentation.scoreText(Double.NaN))
        assertEquals("—", RiskPresentation.scoreText(1.01))
        assertEquals("25% risk score", RiskPresentation.riskScoreText(0.25))
        assertEquals("Risk score unavailable", RiskPresentation.riskScoreText(null))
    }

    @Test
    fun `period text pluralises and hides when absent`() {
        assertEquals("Yesterday · 2 sessions", RiskPresentation.periodText("Yesterday", 2))
        assertEquals("Today · 1 session", RiskPresentation.periodText("Today", 1))
        assertEquals("Today", RiskPresentation.periodText("Today", null))
        assertNull(RiskPresentation.periodText("  ", 3))
        assertNull(RiskPresentation.periodText(null, 3))
    }

    @Test
    fun `detail and scoped texts compose the shared pieces`() {
        assertEquals("34% risk score · Yesterday · 2 sessions",
            RiskPresentation.detailText(0.34, "Yesterday", 2))
        assertEquals("34% risk score", RiskPresentation.detailText(0.34, null, null))
        assertEquals("Risk score unavailable", RiskPresentation.detailText(null, null, null))
        assertEquals("This session: Low concern · 25%",
            RiskPresentation.scopedRiskText("This session", "casual", 0.25))
        assertEquals("Live session: Some concern",
            RiskPresentation.scopedRiskText("Live session", "at_risk", null))
    }
}
