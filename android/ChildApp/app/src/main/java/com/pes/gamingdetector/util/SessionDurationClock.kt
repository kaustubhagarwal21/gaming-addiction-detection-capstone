package com.pes.gamingdetector.util

/**
 * Bridges a persisted epoch session start to a monotonic in-process duration.
 *
 * The epoch baseline lets a restarted process resume the displayed duration. Once
 * constructed, later wall-clock corrections cannot move the timer forward/backward.
 */
class SessionDurationClock(
    sessionStartedAtEpochMs: Long,
    createdAtEpochMs: Long,
    private val createdAtElapsedMs: Long,
) {
    private val elapsedBeforeCreationMs =
        (createdAtEpochMs - sessionStartedAtEpochMs).coerceAtLeast(0L)

    fun elapsedMs(nowElapsedMs: Long): Long =
        elapsedBeforeCreationMs +
            (nowElapsedMs - createdAtElapsedMs).coerceAtLeast(0L)
}
