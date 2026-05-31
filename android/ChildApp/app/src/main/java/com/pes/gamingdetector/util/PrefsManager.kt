package com.pes.gamingdetector.util

import android.content.Context
import android.content.SharedPreferences
import com.pes.gamingdetector.api.ApiClient

class PrefsManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences(Constants.PREFS_NAME, Context.MODE_PRIVATE)

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

    fun isLoggedIn() = userId != -1

    fun hasActiveSession() = activeSessionId != -1

    fun clearSession() {
        activeSessionId = -1
        activeSessionGame = ""
        activeSessionPackage = ""
        activeSessionStart = 0L
    }

    fun logout() {
        val savedUrl = serverUrl
        prefs.edit().clear().apply()
        serverUrl = savedUrl
        ApiClient.authToken = null
    }
}
