package com.pes.parentmonitor.util

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import com.pes.parentmonitor.BuildConfig
import com.pes.parentmonitor.api.ApiClient

class PrefsManager(context: Context) {
    // Encrypted at rest (EncryptedSharedPreferences); migrates the legacy plaintext store once.
    private val prefs: SharedPreferences = SecurePrefs.get(context, Constants.PREFS_NAME)

    init {
        // Bind legacy tokens (which predate KEY_AUTH_ORIGIN) to the server that was
        // persisted with them, then restore the atomic token+origin session.
        val token = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
        var origin = prefs.getString(Constants.KEY_AUTH_ORIGIN, null)
        if (!token.isNullOrBlank() && origin.isNullOrBlank()) {
            val rawServer = prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
            origin = ServerUrl.normalize(rawServer, BuildConfig.DEBUG)
                ?.let(ServerOrigin::normalize)
            if (origin != null) {
                prefs.edit().putString(Constants.KEY_AUTH_ORIGIN, origin).apply()
            } else {
                // An invalid/corrupt legacy address cannot safely establish where the
                // persisted bearer token came from. Fail closed and require login.
                prefs.edit()
                    .remove(Constants.KEY_AUTH_TOKEN)
                    .remove(Constants.KEY_AUTH_ORIGIN)
                    .apply()
            }
        }
        ApiClient.restoreAuthSession(
            prefs.getString(Constants.KEY_AUTH_TOKEN, null),
            origin
        )
    }

    var authToken: String?
        get() = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
        set(v) {
            val origin = if (v.isNullOrBlank()) null else ServerOrigin.normalize(serverUrl)
            prefs.edit()
                .putString(Constants.KEY_AUTH_TOKEN, v)
                .putString(Constants.KEY_AUTH_ORIGIN, origin)
                .apply()
            if (v.isNullOrBlank()) ApiClient.clearAuthSession()
            else ApiClient.installAuthSession(v, origin)
        }

    var parentId: Int
        get() = prefs.getInt(Constants.KEY_PARENT_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_PARENT_ID, v).apply()

    var parentName: String
        get() = prefs.getString(Constants.KEY_PARENT_NAME, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_PARENT_NAME, v).apply()

    /** Family binding for data-only FCM pushes. Missing/mismatched pushes are ignored. */
    var familyCode: String
        get() = prefs.getString(Constants.KEY_FAMILY_CODE, "") ?: ""
        set(v) = prefs.edit()
            .putString(Constants.KEY_FAMILY_CODE, v.trim().uppercase())
            .apply()

    var serverUrl: String
        get() = ServerUrl.normalize(
            prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL),
            BuildConfig.DEBUG
        ) ?: Constants.BASE_URL
        set(v) {
            ServerUrl.normalize(v, BuildConfig.DEBUG)?.let { normalized ->
                prefs.edit().putString(Constants.KEY_SERVER_URL, normalized).apply()
            }
        }

    var childUserId: Int
        get() = prefs.getInt(Constants.KEY_CHILD_USER_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_CHILD_USER_ID, v).apply()

    var childName: String
        get() = prefs.getString("child_name", "") ?: ""
        set(v) = prefs.edit().putString("child_name", v).apply()

    var fcmToken: String
        get() = prefs.getString(Constants.KEY_FCM_TOKEN, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_FCM_TOKEN, v).apply()

    // Per-child high-water mark of the last alert we notified about. Keyed by child id
    // because alert ids are global — one shared value suppressed a sibling's alerts in a
    // multi-child family after switching children.
    fun lastNotifiedAlertId(childId: Int): Int =
        prefs.getInt("${Constants.KEY_LAST_ALERT_ID}_$childId", -1)
    fun advanceLastNotifiedAlertId(childId: Int, candidate: Int) {
        synchronized(alertWatermarkLock) {
            val key = "${Constants.KEY_LAST_ALERT_ID}_$childId"
            val current = prefs.getInt(key, -1)
            if (candidate > current) {
                // apply() changes the process-wide SharedPreferences map before it
                // returns, so releasing the lock cannot expose a regressed value.
                prefs.edit().putInt(key, candidate).apply()
            }
        }
    }

    fun isLoggedIn(): Boolean {
        val storedOrigin = prefs.getString(Constants.KEY_AUTH_ORIGIN, null)
        return parentId > 0 &&
            !authToken.isNullOrBlank() &&
            storedOrigin != null &&
            storedOrigin == ServerOrigin.normalize(serverUrl)
    }

    @SuppressLint("ApplySharedPref") // logout state and retained endpoint must be durable together
    fun logout() {
        val savedUrl = serverUrl
        prefs.edit()
            .clear()
            .putString(Constants.KEY_SERVER_URL, savedUrl)
            .commit()
        ApiClient.clearAuthSession()
    }

    private companion object {
        val alertWatermarkLock = Any()
    }
}
