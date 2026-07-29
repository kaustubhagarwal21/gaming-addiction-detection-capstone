package com.pes.gamingdetector.util

/** Pure timing rules for durable automatic-session end retries. */
object SessionEndLogic {
    /**
     * Recompute how long ago play actually stopped for every retry.  Wall-clock rollback is
     * clamped to zero; persisted epoch milliseconds are required so the instant survives a
     * service/process restart.
     */
    fun endedSecondsAgo(stoppedAtMs: Long, nowMs: Long): Long {
        if (stoppedAtMs <= 0L) return 0L
        return ((nowMs - stoppedAtMs).coerceAtLeast(0L)) / 1_000L
    }
}
