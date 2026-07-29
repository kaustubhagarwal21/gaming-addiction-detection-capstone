package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Test

class SessionDurationClockTest {

    @Test
    fun `duration advances only with monotonic time after construction`() {
        val clock = SessionDurationClock(
            sessionStartedAtEpochMs = 10_000L,
            createdAtEpochMs = 15_000L,
            createdAtElapsedMs = 2_000L,
        )

        assertEquals(5_000L, clock.elapsedMs(2_000L))
        assertEquals(8_500L, clock.elapsedMs(5_500L))
    }

    @Test
    fun `future epoch start and elapsed rollback are clamped`() {
        val clock = SessionDurationClock(
            sessionStartedAtEpochMs = 20_000L,
            createdAtEpochMs = 15_000L,
            createdAtElapsedMs = 7_000L,
        )

        assertEquals(0L, clock.elapsedMs(6_000L))
    }
}
