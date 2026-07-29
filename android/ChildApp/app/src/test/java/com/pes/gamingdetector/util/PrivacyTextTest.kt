package com.pes.gamingdetector.util

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PrivacyTextTest {
    @Test
    fun `server consent is honored only for the exact bundled policy version`() {
        assertTrue(PrivacyText.matchesServerVersion(PrivacyText.CONSENT_VERSION))
        assertFalse(PrivacyText.matchesServerVersion(null))
        assertFalse(PrivacyText.matchesServerVersion(""))
        assertFalse(PrivacyText.matchesServerVersion("2026-07-29"))
        assertFalse(PrivacyText.matchesServerVersion(" ${PrivacyText.CONSENT_VERSION} "))
    }
}
