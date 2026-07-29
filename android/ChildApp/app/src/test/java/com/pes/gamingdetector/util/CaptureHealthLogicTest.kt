package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CaptureHealthLogicTest {
    @Test
    fun `first observation does not nag an unconfigured child`() {
        assertNull(CaptureHealthLogic.loss(null, "00"))
        assertNull(CaptureHealthLogic.loss("", "00"))
    }

    @Test
    fun `persisted keyboard regression is detected after process restart`() {
        assertEquals(
            CaptureHealthLogic.Loss.KEYBOARD,
            CaptureHealthLogic.loss("11", "10")
        )
    }

    @Test
    fun `persisted accessibility regression is detected after process restart`() {
        assertEquals(
            CaptureHealthLogic.Loss.ACCESSIBILITY,
            CaptureHealthLogic.loss("11", "01")
        )
    }

    @Test
    fun `unchanged and recovery transitions do not notify`() {
        assertNull(CaptureHealthLogic.loss("11", "11"))
        assertNull(CaptureHealthLogic.loss("00", "11"))
        assertNull(CaptureHealthLogic.loss("00", "00"))
    }
}
