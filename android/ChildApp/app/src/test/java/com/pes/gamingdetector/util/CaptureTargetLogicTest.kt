package com.pes.gamingdetector.util

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CaptureTargetLogicTest {
    @Test
    fun `only exact nonblank session and editor packages are safe`() {
        assertTrue(CaptureTargetLogic.isExactSessionTarget("com.game", "com.game"))
        assertFalse(CaptureTargetLogic.isExactSessionTarget("com.game", "com.chat"))
        assertFalse(CaptureTargetLogic.isExactSessionTarget("", "com.game"))
        assertFalse(CaptureTargetLogic.isExactSessionTarget("com.game", null))
    }
}
