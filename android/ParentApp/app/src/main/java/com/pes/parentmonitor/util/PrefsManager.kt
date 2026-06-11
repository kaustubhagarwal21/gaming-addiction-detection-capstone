package com.pes.parentmonitor.util

import android.content.Context
import android.content.SharedPreferences
import com.pes.parentmonitor.api.ApiClient

class PrefsManager(context: Context) {
    // Encrypted at rest (EncryptedSharedPreferences); migrates the legacy plaintext store once.
    private val prefs: SharedPreferences = SecurePrefs.get(context, Constants.PREFS_NAME)

    init {
        // Refresh the in-memory bearer token from disk whenever a PrefsManager is
        // created (every Activity/Service does this before calling the API), so the
        // token survives process death and service restarts.
        ApiClient.authToken = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
    }

    var authToken: String?
        get() = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
        set(v) {
            prefs.edit().putString(Constants.KEY_AUTH_TOKEN, v).apply()
            ApiClient.authToken = v
        }

    var parentId: Int
        get() = prefs.getInt(Constants.KEY_PARENT_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_PARENT_ID, v).apply()

    var parentName: String
        get() = prefs.getString(Constants.KEY_PARENT_NAME, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_PARENT_NAME, v).apply()

    var serverUrl: String
        get() = prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL) ?: Constants.BASE_URL
        set(v) = prefs.edit().putString(Constants.KEY_SERVER_URL, v).apply()

    var childUserId: Int
        get() = prefs.getInt(Constants.KEY_CHILD_USER_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_CHILD_USER_ID, v).apply()

    var childName: String
        get() = prefs.getString("child_name", "") ?: ""
        set(v) = prefs.edit().putString("child_name", v).apply()

    var lastRiskLevel: String
        get() = prefs.getString(Constants.KEY_LAST_RISK_LEVEL, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_LAST_RISK_LEVEL, v).apply()

    var fcmToken: String
        get() = prefs.getString(Constants.KEY_FCM_TOKEN, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_FCM_TOKEN, v).apply()

    // Per-child high-water mark of the last alert we notified about. Keyed by child id
    // because alert ids are global — one shared value suppressed a sibling's alerts in a
    // multi-child family after switching children.
    fun lastNotifiedAlertId(childId: Int): Int =
        prefs.getInt("${Constants.KEY_LAST_ALERT_ID}_$childId", -1)
    fun setLastNotifiedAlertId(childId: Int, v: Int) =
        prefs.edit().putInt("${Constants.KEY_LAST_ALERT_ID}_$childId", v).apply()

    fun isLoggedIn() = parentId != -1

    fun logout() {
        val savedUrl = serverUrl
        prefs.edit().clear().apply()
        serverUrl = savedUrl
        ApiClient.authToken = null
    }
}
