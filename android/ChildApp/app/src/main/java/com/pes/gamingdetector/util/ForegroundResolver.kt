package com.pes.gamingdetector.util

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context

/**
 * Authoritative "what app is in the foreground right now" resolver.
 *
 * Primary signal: UsageStatsManager's most-recent ACTIVITY_RESUMED across all
 * packages over a wide window. This is reliable for BOTH:
 *   - continuous gameplay (the game's resume event stays the most recent; no
 *     other app has resumed since), and
 *   - leaving the game (the launcher / next app fires a newer resume).
 *
 * Why not TYPE_WINDOW_STATE_CHANGED (ForegroundTracker)? Window-state events
 * fire once when a window appears and DON'T re-fire while a SurfaceView-based
 * game renders. A transient launcher/overlay event then sticks permanently,
 * making the tracker report the wrong app for the rest of the session. We keep
 * ForegroundTracker only as a fallback for the rare case UsageStats returns
 * nothing.
 *
 * Results are cached for CACHE_MS so this is cheap to call per-keystroke from
 * the accessibility service.
 */
object ForegroundResolver {

    private const val CACHE_MS = 2_000L
    private const val WINDOW_MS = 24 * 60 * 60_000L  // wide: a session can run for hours

    @Volatile private var cachedPkg: String? = null
    @Volatile private var cachedAt: Long = 0L

    fun current(context: Context): String? {
        val now = System.currentTimeMillis()
        if (now - cachedAt < CACHE_MS) return cachedPkg
        val pkg = queryUsageStats(context) ?: ForegroundTracker.current()
        cachedPkg = pkg
        cachedAt = now
        return pkg
    }

    /** Force a fresh read on the next call (e.g. right after a session starts). */
    fun invalidate() {
        cachedAt = 0L
    }

    /**
     * The package whose ACTIVITY_RESUMED is the most recent across all apps.
     *
     * This is the reliable "what app is on screen" signal: it stays on the game
     * during continuous play (no other app resumes), and switches the moment the
     * user opens another app. We deliberately do NOT factor in PAUSED/STOPPED here
     * — on some devices background apps fire those constantly, which would wrongly
     * report "no foreground". The screen-locked case (where the game stays the most
     * recent RESUMED forever) is handled separately by PassiveMonitorService via the
     * SCREEN_OFF broadcast.
     */
    private fun queryUsageStats(context: Context): String? {
        return try {
            val usm = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val now = System.currentTimeMillis()
            val events = usm.queryEvents(now - WINDOW_MS, now)
            var lastPkg: String? = null
            var lastTime = 0L
            val ev = UsageEvents.Event()
            while (events.hasNextEvent()) {
                events.getNextEvent(ev)
                if (ev.eventType == UsageEvents.Event.ACTIVITY_RESUMED && ev.timeStamp > lastTime) {
                    lastTime = ev.timeStamp
                    lastPkg = ev.packageName
                }
            }
            lastPkg
        } catch (_: Exception) { null }
    }
}
