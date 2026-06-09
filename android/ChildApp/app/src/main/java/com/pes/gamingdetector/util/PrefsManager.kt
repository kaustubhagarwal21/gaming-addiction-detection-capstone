package com.pes.gamingdetector.util

import android.content.Context
import android.content.SharedPreferences
import com.pes.gamingdetector.api.ApiClient

class PrefsManager(context: Context) {
    // Encrypted at rest (EncryptedSharedPreferences); migrates the legacy plaintext store once.
    private val prefs: SharedPreferences = SecurePrefs.get(context, Constants.PREFS_NAME)

    init {
        // Refresh the in-memory bearer token from disk whenever a PrefsManager is
        // created (every Activity/Service does this before calling the API), so the
        // token survives process death and the monitoring/voice service restarts.
        ApiClient.authToken = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
    }

    var authToken: String?
        get() = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
        set(v) {
            prefs.edit().putString(Constants.KEY_AUTH_TOKEN, v).apply()
            ApiClient.authToken = v
        }

    var userId: Int
        get() = prefs.getInt(Constants.KEY_USER_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_USER_ID, v).apply()

    var userName: String
        get() = prefs.getString(Constants.KEY_USER_NAME, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_USER_NAME, v).apply()

    var serverUrl: String
        get() = prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL) ?: Constants.BASE_URL
        set(v) = prefs.edit().putString(Constants.KEY_SERVER_URL, v).apply()

    var activeSessionId: Int
        get() = prefs.getInt(Constants.KEY_ACTIVE_SESSION_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_ACTIVE_SESSION_ID, v).apply()

    var activeSessionGame: String
        get() = prefs.getString(Constants.KEY_ACTIVE_SESSION_GAME, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_ACTIVE_SESSION_GAME, v).apply()

    var activeSessionPackage: String
        get() = prefs.getString(Constants.KEY_ACTIVE_SESSION_PKG, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_ACTIVE_SESSION_PKG, v).apply()

    var activeSessionStart: Long
        get() = prefs.getLong(Constants.KEY_ACTIVE_SESSION_START, 0L)
        set(v) = prefs.edit().putLong(Constants.KEY_ACTIVE_SESSION_START, v).apply()

    var childCode: String
        get() = prefs.getString(Constants.KEY_CHILD_CODE, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_CHILD_CODE, v).apply()

    var onboardingDone: Boolean
        get() = prefs.getBoolean("onboarding_done", false)
        set(v) = prefs.edit().putBoolean("onboarding_done", v).apply()

    var consentDone: Boolean
        get() = prefs.getBoolean("consent_done", false)
        set(v) = prefs.edit().putBoolean("consent_done", v).apply()

    // Daily check-in gamification (local): a streak the child grows by checking in each day.
    var checkinStreak: Int
        get() = prefs.getInt("checkin_streak", 0)
        set(v) = prefs.edit().putInt("checkin_streak", v).apply()

    var lastCheckinDate: String
        get() = prefs.getString("last_checkin_date", "") ?: ""
        set(v) = prefs.edit().putString("last_checkin_date", v).apply()

    // Device-admin (uninstall protection) is optional and offered once, so it doesn't nag.
    var deviceAdminOffered: Boolean
        get() = prefs.getBoolean("device_admin_offered", false)
        set(v) = prefs.edit().putBoolean("device_admin_offered", v).apply()

    // Policy version the user actually agreed to. When the shipped CONSENT_VERSION
    // is newer than this, consent is requested again (the policy materially changed).
    var consentVersion: String
        get() = prefs.getString("consent_version", "") ?: ""
        set(v) = prefs.edit().putString("consent_version", v).apply()

    // Packages the parent manually marked as games (force-include). Covers a real game
    // the OS doesn't report as CATEGORY_GAME and that isn't in the curated list.
    var forcedGamePackages: Set<String>
        get() = prefs.getStringSet("forced_game_pkgs", emptySet()) ?: emptySet()
        set(v) = prefs.edit().putStringSet("forced_game_pkgs", HashSet(v)).apply()

    // Packages the parent marked as NOT a game (force-exclude). Stops monitoring a
    // non-game the OS miscategorised as a game, or a game they don't want tracked.
    var excludedGamePackages: Set<String>
        get() = prefs.getStringSet("excluded_game_pkgs", emptySet()) ?: emptySet()
        set(v) = prefs.edit().putStringSet("excluded_game_pkgs", HashSet(v)).apply()

    fun isLoggedIn() = userId != -1

    fun hasActiveSession() = activeSessionId != -1

    fun clearSession() {
        activeSessionId = -1
        activeSessionGame = ""
        activeSessionPackage = ""
        activeSessionStart = 0L
    }

    fun logout() {
        // Preserve device-level config that isn't tied to the account: the server URL
        // and the parent's game overrides (set during setup, survive re-login).
        val savedUrl = serverUrl
        val savedIncluded = forcedGamePackages
        val savedExcluded = excludedGamePackages
        prefs.edit().clear().apply()
        serverUrl = savedUrl
        forcedGamePackages = savedIncluded
        excludedGamePackages = savedExcluded
        ApiClient.authToken = null
    }
}
