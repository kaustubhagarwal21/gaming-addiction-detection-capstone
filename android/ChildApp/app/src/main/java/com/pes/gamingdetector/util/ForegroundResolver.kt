package com.pes.gamingdetector.util

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.SystemClock

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
    private const val FULL_WINDOW_MS = 24 * 60 * 60_000L  // first scan only: a session can run for hours
    private const val OVERLAP_MS = 5_000L                 // re-read a short tail for late-logged events

    @Volatile private var cachedPkg: String? = null
    @Volatile private var cachedAt: Long = 0L

    /** Most recent ACTIVITY_RESUMED seen so far. Immutable holder so a reader can
     *  never observe one scan's package paired with another scan's timestamp. */
    private class Champion(val pkg: String?, val time: Long)
    @Volatile private var champion = Champion(null, 0L)

    fun current(context: Context): String? {
        val now = SystemClock.elapsedRealtime()
        if (now - cachedAt < CACHE_MS) return cachedPkg
        val pkg = queryUsageStats(context) ?: ForegroundTracker.current()
        cachedPkg = pkg
        cachedAt = now
        return pkg
    }

    /** Capture/privacy decisions must not use the normal 2-second performance cache. */
    fun currentFresh(context: Context): String? {
        invalidate()
        return current(context)
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
     *
     * INCREMENTAL: only events newer than the remembered champion (plus a small
     * overlap) are scanned. The old code re-read the full 24-hour window on every
     * call — and the capture paths call this per keystroke via currentFresh(), so
     * iterating a whole day of UsageEvents ran on the accessibility thread for each
     * key tap. The champion carries across calls: during continuous play no newer
     * RESUMED arrives and the game keeps winning without re-reading its hours-old
     * event, so the semantics are unchanged while each call stays cheap.
     */
    private fun queryUsageStats(context: Context): String? {
        return try {
            val usm = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val now = System.currentTimeMillis()
            var champ = champion
            if (champ.time > now) {
                // Wall clock rolled back past the champion's event: its timestamp would
                // out-rank every future event forever. Drop it and rescan from scratch.
                champ = Champion(null, 0L)
            }
            val begin = if (champ.time > 0L) {
                maxOf(champ.time - OVERLAP_MS, now - FULL_WINDOW_MS)
            } else {
                now - FULL_WINDOW_MS
            }
            val events = usm.queryEvents(begin, now)
            var lastPkg = champ.pkg
            var lastTime = champ.time
            val ev = UsageEvents.Event()
            while (events.hasNextEvent()) {
                events.getNextEvent(ev)
                if (ev.eventType == UsageEvents.Event.ACTIVITY_RESUMED && ev.timeStamp > lastTime) {
                    lastTime = ev.timeStamp
                    lastPkg = ev.packageName
                }
            }
            // A racing thread may overwrite with a slightly older champion; the next
            // call's overlap re-scan then re-finds the newer event, so it self-heals.
            champion = Champion(lastPkg, lastTime)
            lastPkg
        } catch (_: Exception) { null }
    }
}
