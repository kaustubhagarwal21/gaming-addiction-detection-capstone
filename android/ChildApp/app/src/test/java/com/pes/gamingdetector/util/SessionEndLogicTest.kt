package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Test

class SessionEndLogicTest {
    @Test
    fun `retry preserves all time since original stop`() {
        val stoppedAt = 1_000_000L
        assertEquals(20L, SessionEndLogic.endedSecondsAgo(stoppedAt, stoppedAt + 20_999L))
        assertEquals(3_620L,
            SessionEndLogic.endedSecondsAgo(stoppedAt, stoppedAt + 3_620_000L))
    }

    @Test
    fun `missing timestamp and wall clock rollback clamp to zero`() {
        assertEquals(0L, SessionEndLogic.endedSecondsAgo(0L, 10_000L))
        assertEquals(0L, SessionEndLogic.endedSecondsAgo(20_000L, 10_000L))
    }
}
