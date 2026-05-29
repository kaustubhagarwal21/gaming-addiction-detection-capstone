package com.pes.gamingdetector.util

/**
 * Process-local cache of the current foreground app, populated by
 * ChatAccessibilityService's TYPE_WINDOW_STATE_CHANGED events.
 *
 * AccessibilityService is push-based and authoritative — the moment the
 * foreground window changes, this object is updated. PassiveMonitorService
 * reads this as its primary foreground signal and only falls back to
 * UsageStatsManager when this has no data yet (service just started, or
 * accessibility permission not granted).
 *
 * IME/system-UI packages are filtered out so transient keyboard or
 * notification-shade events don't overwrite the real foreground.
 */
object ForegroundTracker {

    @Volatile private var currentPkg: String? = null
    @Volatile private var lastChangeAt: Long = 0L

    private val IGNORE_PREFIXES = listOf(
        "com.android.systemui",
        "com.android.inputmethod",
        "com.google.android.inputmethod",
        "com.samsung.android.honeyboard",
        "com.touchtype.swiftkey",
    )

    fun update(pkg: String?) {
        if (pkg.isNullOrEmpty() || pkg == "android") return
        if (IGNORE_PREFIXES.any { pkg.startsWith(it) }) return
        currentPkg = pkg
        lastChangeAt = System.currentTimeMillis()
    }

    fun current(): String? = currentPkg
    fun lastChangeAt(): Long = lastChangeAt
}
