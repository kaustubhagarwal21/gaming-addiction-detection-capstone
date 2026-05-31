package com.pes.gamingdetector.util

import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Build

/**
 * Decides whether a foreground package is a game, and what to display it as.
 *
 * A package counts as a game if it's in the curated [Constants.PACKAGE_TO_GAME] list
 * (which gives nice names) OR the OS marks it as [ApplicationInfo.CATEGORY_GAME] — so
 * monitoring works for ANY installed game without maintaining a list. Lookups are
 * cached because the monitor polls every few seconds.
 *
 * Reading another app's category on Android 11+ needs the QUERY_ALL_PACKAGES
 * permission (declared in the manifest; fine for sideload distribution).
 */
object GameDetector {
    private val cache = HashMap<String, Boolean>()

    fun isGame(ctx: Context, pkg: String?): Boolean {
        if (pkg.isNullOrEmpty()) return false
        if (pkg in Constants.KNOWN_GAMING_PACKAGES) return true
        cache[pkg]?.let { return it }
        val result = try {
            val ai = ctx.packageManager.getApplicationInfo(pkg, 0)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ai.category == ApplicationInfo.CATEGORY_GAME
            } else {
                @Suppress("DEPRECATION")
                (ai.flags and ApplicationInfo.FLAG_IS_GAME) != 0
            }
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
