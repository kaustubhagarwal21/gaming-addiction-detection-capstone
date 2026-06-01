package com.pes.gamingdetector.util

import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Build

/**
 * Decides whether a foreground package is a game, and what to display it as.
 *
 * Layered so it's robust for ANY installed game without a maintained list, while
 * resisting both false positives (a non-game bucketed as a game) and false negatives
 * (a real game mis-reporting its category):
 *   1. Curated allowlist ([Constants.KNOWN_GAMING_PACKAGES]) → always a game. Catches
 *      popular titles even if they report the wrong category.
 *   2. Denylist of system / store / launcher namespaces → never a game. Kills the
 *      common false positives (Play Store, Play Games hub, GMS, OEM launchers, us).
 *   3. Otherwise: OS [ApplicationInfo.CATEGORY_GAME] AND the package is launchable.
 *      The launchable check rejects background/system packages that merely report a
 *      game category but aren't something a child opens and plays.
 * Lookups are cached because the monitor polls every few seconds.
 *
 * Reading another app's category on Android 11+ needs the QUERY_ALL_PACKAGES
 * permission (declared in the manifest; fine for sideload distribution).
 */
object GameDetector {
    private val cache = HashMap<String, Boolean>()

    // Namespaces that can report (or get bucketed under) a game category but are never
    // "the child playing a game": OS/system, Google services, the Play Store, the Play
    // Games hub, common OEM launchers, and our own apps. Matched as exact or dot-prefix.
    private val NON_GAME_PREFIXES = listOf(
        "com.android",                    // AOSP system + Play Store (com.android.vending)
        "com.google.android.gms",         // Play services (sign-in, ads, consent)
        "com.google.android.gsf",
        "com.google.android.play.games",  // Play Games hub app (not a game itself)
        "com.google.android.packageinstaller",
        "com.sec.android",                // Samsung system
        "com.samsung.android",
        "com.miui", "com.mi.android", "com.xiaomi",  // Xiaomi system/launcher
        "com.coloros", "com.oppo", "com.oneplus", "com.vivo", "com.heytap",  // OEM
        "com.pes.gamingdetector",         // ourselves
        "com.pes.parentmonitor",
    )

    private fun isNonGameNamespace(pkg: String) =
        NON_GAME_PREFIXES.any { pkg == it || pkg.startsWith("$it.") }

    fun isGame(ctx: Context, pkg: String?): Boolean {
        if (pkg.isNullOrEmpty()) return false
        if (pkg in Constants.KNOWN_GAMING_PACKAGES) return true   // allowlist wins
        if (isNonGameNamespace(pkg)) return false                 // denylist kills false positives
        cache[pkg]?.let { return it }
        val result = try {
            val pm = ctx.packageManager
            val ai = pm.getApplicationInfo(pkg, 0)
            val isGameCategory = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ai.category == ApplicationInfo.CATEGORY_GAME
            } else {
                @Suppress("DEPRECATION")
                (ai.flags and ApplicationInfo.FLAG_IS_GAME) != 0
            }
            // A real, playable game has a launcher entry; reject category-only system pkgs.
            isGameCategory && pm.getLaunchIntentForPackage(pkg) != null
        } catch (_: Exception) {
            false
        }
        cache[pkg] = result
        return result
    }

    /** Curated name if known, else the app's own label, else a tidy package fallback. */
    fun displayName(ctx: Context, pkg: String): String {
        Constants.PACKAGE_TO_GAME[pkg]?.let { return it }
        return try {
            val pm = ctx.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        } catch (_: Exception) {
            pkg.substringAfterLast('.').replaceFirstChar { it.uppercase() }
        }
    }
}
