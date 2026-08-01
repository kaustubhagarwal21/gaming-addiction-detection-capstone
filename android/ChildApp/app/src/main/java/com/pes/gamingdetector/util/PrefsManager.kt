package com.pes.gamingdetector.util

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import com.pes.gamingdetector.BuildConfig
import com.pes.gamingdetector.api.ApiClient

class PrefsManager(context: Context) {
    // Encrypted at rest (EncryptedSharedPreferences); migrates the legacy plaintext store once.
    private val prefs: SharedPreferences = SecurePrefs.get(context, Constants.PREFS_NAME)

    init {
        // Refresh the in-memory bearer token from disk whenever a PrefsManager is
        // created (every Activity/Service does this before calling the API), so the
        // token survives process death and the monitoring/voice service restarts.
        val token = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
        var authServer = prefs.getString(Constants.KEY_AUTH_SERVER_URL, null)
        if (!token.isNullOrBlank()) {
            // Migrate tokens created before KEY_AUTH_SERVER_URL existed, but only when
            // the issuing server can be reconstructed under today's validation policy.
            val candidate = authServer
                ?: prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
            authServer = candidate?.let {
                ServerUrl.normalize(it, allowInsecureLan = BuildConfig.DEBUG)
            }
            if (authServer == null) {
                // A token with an unknown/unsafe issuing server must never be attached to
                // a fallback endpoint. Fail closed and require a fresh login.
                prefs.edit()
                    .remove(Constants.KEY_AUTH_TOKEN)
                    .remove(Constants.KEY_AUTH_SERVER_URL)
                    .apply()
            } else if (prefs.getString(Constants.KEY_AUTH_SERVER_URL, null) != authServer) {
                // Write only when the stored value actually changes. PrefsManager is
                // constructed on hot paths, and unconditionally re-writing the same
                // value queued an encrypted disk write per construction.
                prefs.edit()
                    .putString(Constants.KEY_AUTH_SERVER_URL, authServer)
                    .apply()
            }
        }
        ApiClient.restorePersistedToken(
            prefs.getString(Constants.KEY_AUTH_TOKEN, null),
            authServer
        )
    }

    var authToken: String?
        get() = prefs.getString(Constants.KEY_AUTH_TOKEN, null)
        set(v) {
            val normalizedServer = if (v.isNullOrBlank()) null else serverUrl
            prefs.edit()
                .putString(Constants.KEY_AUTH_TOKEN, v)
                .putString(Constants.KEY_AUTH_SERVER_URL,
                    if (v.isNullOrBlank()) null else normalizedServer)
                .apply()
            // The public setter is used only after login/registration. Restores during
            // Activity/Service construction go through restorePersistedToken() above and
            // deliberately do not re-arm an invalidated token.
            if (v.isNullOrBlank()) ApiClient.clearAuthToken()
            else ApiClient.installLoginToken(v, normalizedServer)
        }

    var userId: Int
        get() = prefs.getInt(Constants.KEY_USER_ID, -1)
        set(v) = prefs.edit().putInt(Constants.KEY_USER_ID, v).apply()

    var userName: String
        get() = prefs.getString(Constants.KEY_USER_NAME, "") ?: ""
        set(v) = prefs.edit().putString(Constants.KEY_USER_NAME, v).apply()

    var serverUrl: String
        get() = ServerUrl.normalize(
            prefs.getString(Constants.KEY_SERVER_URL, Constants.BASE_URL)
                ?: Constants.BASE_URL,
            allowInsecureLan = BuildConfig.DEBUG
        ) ?: Constants.BASE_URL
        set(v) {
            ServerUrl.normalize(v, allowInsecureLan = BuildConfig.DEBUG)?.let { normalized ->
                prefs.edit().putString(Constants.KEY_SERVER_URL, normalized).apply()
            }
        }

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

    val pendingEndSessionId: Int
        get() = prefs.getInt(Constants.KEY_PENDING_END_SESSION_ID, -1)

    val pendingEndStoppedAt: Long
        get() = prefs.getLong(Constants.KEY_PENDING_END_STOPPED_AT, 0L)

    /** Persist the actual last-playing instant before making the end request. */
    @SuppressLint("ApplySharedPref")
    fun markPendingEnd(sessionId: Int, stoppedAtMs: Long): Boolean {
        if (sessionId <= 0 || stoppedAtMs <= 0L) return false
        return prefs.edit()
            .putInt(Constants.KEY_PENDING_END_SESSION_ID, sessionId)
            .putLong(Constants.KEY_PENDING_END_STOPPED_AT, stoppedAtMs)
            .commit()
    }

    @SuppressLint("ApplySharedPref")
    fun clearPendingEnd(): Boolean = prefs.edit()
        .remove(Constants.KEY_PENDING_END_SESSION_ID)
        .remove(Constants.KEY_PENDING_END_STOPPED_AT)
        .commit()

    // Marks a game whose session START failed because the device was offline (server
    // unreachable / Render cold-start). If connectivity returns while the SAME game is
    // still playing, the interval from this start is back-filled as a real session.
    val offlineSessionStartMs: Long
        get() = prefs.getLong("offline_session_start", 0L)
    val offlineSessionGame: String
        get() = prefs.getString("offline_session_game", "") ?: ""
    val offlineSessionPackage: String
        get() = prefs.getString("offline_session_package", "") ?: ""
    val offlineSessionKey: String
        get() = prefs.getString("offline_session_key", "") ?: ""
    val offlineSessionLastSeenMs: Long
        get() = prefs.getLong("offline_session_last_seen", 0L)

    /** Persist the whole marker in one committed edit. Separate writes could leave a start
     *  without its game/key when the process was killed between writes, making the
     *  supposedly durable offline session impossible to deliver. */
    @SuppressLint("ApplySharedPref") // monitor runs on Dispatchers.IO; durability is required
    fun markOfflineSession(
        game: String,
        packageName: String,
        startMs: Long,
        key: String,
        lastSeenMs: Long = startMs
    ) {
        prefs.edit()
            .putLong("offline_session_start", startMs)
            .putString("offline_session_game", game)
            .putString("offline_session_package", packageName)
            .putString("offline_session_key", key)
            .putLong("offline_session_last_seen", lastSeenMs)
            .commit()
    }

    /** Checkpoint the last tick on which the offline game was definitely foreground.
     *  Debounced by the caller so encrypted preferences are not written every 5 seconds. */
    @SuppressLint("ApplySharedPref") // monitor runs on Dispatchers.IO
    fun touchOfflineSession(seenMs: Long) {
        prefs.edit().putLong("offline_session_last_seen", seenMs).commit()
    }

    @SuppressLint("ApplySharedPref") // monitor runs on Dispatchers.IO; order matters
    fun clearOfflineSession() {
        prefs.edit()
            .remove("offline_session_start")
            .remove("offline_session_game")
            .remove("offline_session_package")
            .remove("offline_session_key")
            .remove("offline_session_last_seen")
            .commit()
    }

    /** Last capture-permission state observed by the monitor (accessibility + IME).
     *  Persisting it lets a reboot/process restart still detect an ON -> OFF regression. */
    var lastCaptureBits: String
        get() = prefs.getString("last_capture_bits", "") ?: ""
        set(v) = prefs.edit().putString("last_capture_bits", v).apply()

    /** Whether the recorder actually opened the microphone for the current session.
     * null = not attempted/legacy, false = blocked or failed, true = actively recording. */
    var voiceCaptureActive: Boolean?
        get() = when (prefs.getInt("voice_capture_active", -1)) {
            0 -> false
            1 -> true
            else -> null
        }
        set(v) {
            prefs.edit().putInt("voice_capture_active", when (v) {
                true -> 1
                false -> 0
                null -> -1
            }).apply()
        }

    // The family code (shown at registration, returned again on every login) — kept so
    // Settings can always display it; without this it was shown exactly once and easily
    // forgotten, locking the parent out of the Parent app.
    var familyCode: String
        get() = prefs.getString("family_code", "") ?: ""
        set(v) = prefs.edit().putString("family_code", v).apply()

    var onboardingDone: Boolean
        get() = prefs.getBoolean("onboarding_done", false)
        set(v) = prefs.edit().putBoolean("onboarding_done", v).apply()

    var consentDone: Boolean
        get() = prefs.getBoolean("consent_done", false)
        set(v) = prefs.edit().putBoolean("consent_done", v).apply()

    // Consent is trusted only after the server accepts a parent-authorized grant.
    var consentSynced: Boolean
        get() = prefs.getBoolean("consent_synced", false)
        set(v) = prefs.edit().putBoolean("consent_synced", v).apply()

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

    // Battery-optimisation exemption is asked once (it keeps monitoring alive under
    // Doze/OEM power killers); declining shouldn't nag on every resume.
    var batteryExemptOffered: Boolean
        get() = prefs.getBoolean("battery_exempt_offered", false)
        set(v) = prefs.edit().putBoolean("battery_exempt_offered", v).apply()

    // Policy version the user actually agreed to. When the shipped CONSENT_VERSION
    // is newer than this, consent is requested again (the policy materially changed).
    var consentVersion: String
        get() = prefs.getString("consent_version", "") ?: ""
        set(v) = prefs.edit().putString("consent_version", v).apply()

    /** Persist the three consent facts atomically only after a successful server grant. */
    @SuppressLint("ApplySharedPref")
    fun saveAcceptedConsent(version: String): Boolean =
        prefs.edit()
            .putBoolean("consent_done", true)
            .putString("consent_version", version)
            .putBoolean("consent_synced", true)
            .commit()

    /** Drop local consent because the SERVER refused data under the current policy
     *  (withdrawal, or a policy version this build predates). Local flags are otherwise
     *  the only gate on capture, so without this the device keeps recording — mic
     *  included — for as long as it stays out of HomeActivity, even though every upload
     *  is being rejected. Durable: a process restart must not resurrect consent. */
    @SuppressLint("ApplySharedPref")
    fun revokeConsentLocally(): Boolean =
        prefs.edit()
            .putBoolean("consent_done", false)
            .putBoolean("consent_synced", false)
            .remove("consent_version")
            .commit()

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

    fun isLoggedIn(): Boolean {
        val authServer = prefs.getString(Constants.KEY_AUTH_SERVER_URL, null)?.let {
            ServerUrl.normalize(it, allowInsecureLan = BuildConfig.DEBUG)
        }
        return userId > 0 &&
            !authToken.isNullOrBlank() &&
            authServer != null &&
            authServer == serverUrl
    }

    fun hasActiveSession() = activeSessionId != -1

    /** Persist a newly allocated server session as one durable transaction. Four separate
     * apply() calls could leave an id without its package/start after process death. */
    @SuppressLint("ApplySharedPref") // called from the monitor IO coroutine; durability is required
    fun saveActiveSession(id: Int, game: String, packageName: String, startMs: Long): Boolean =
        prefs.edit()
            .putInt(Constants.KEY_ACTIVE_SESSION_ID, id)
            .putString(Constants.KEY_ACTIVE_SESSION_GAME, game)
            .putString(Constants.KEY_ACTIVE_SESSION_PKG, packageName)
            .putLong(Constants.KEY_ACTIVE_SESSION_START, startMs)
            .remove(Constants.KEY_PENDING_END_SESSION_ID)
            .remove(Constants.KEY_PENDING_END_STOPPED_AT)
            .commit()

    @SuppressLint("ApplySharedPref")
    fun clearSession() {
        // Durable because a process death after a confirmed server end must not resurrect
        // the old session (or its pending-end retry marker) on boot.
        prefs.edit()
            .putInt(Constants.KEY_ACTIVE_SESSION_ID, -1)
            .putString(Constants.KEY_ACTIVE_SESSION_GAME, "")
            .putString(Constants.KEY_ACTIVE_SESSION_PKG, "")
            .putLong(Constants.KEY_ACTIVE_SESSION_START, 0L)
            .remove(Constants.KEY_PENDING_END_SESSION_ID)
            .remove(Constants.KEY_PENDING_END_STOPPED_AT)
            .commit()
    }

    fun hasCurrentConsent(): Boolean =
        consentDone && consentVersion == PrivacyText.CONSENT_VERSION

    /** Every always-on/capture component uses the same fail-closed eligibility gate. */
    fun canMonitor(): Boolean =
        isLoggedIn() && !authToken.isNullOrBlank() && hasCurrentConsent()

    fun logout() {
        // Preserve device-level config that isn't tied to the account: the server URL
        // and the parent's game overrides (set during setup, survive re-login).
        val savedUrl = serverUrl
        val savedIncluded = forcedGamePackages
        val savedExcluded = excludedGamePackages
        val savedCaptureBits = lastCaptureBits
        // One durable edit prevents process death between clear() and the separate
        // restore writes from losing device-level configuration.
        prefs.edit().clear()
            .putString(Constants.KEY_SERVER_URL, savedUrl)
            .putStringSet("forced_game_pkgs", HashSet(savedIncluded))
            .putStringSet("excluded_game_pkgs", HashSet(savedExcluded))
            .putString("last_capture_bits", savedCaptureBits)
            .commit()
        ApiClient.clearAuthToken()
    }
}
