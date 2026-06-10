package com.pes.parentmonitor.util

object Constants {
    // Cloud backend (Render). Override in Settings → Server URL for local dev
    // (e.g. http://127.0.0.1:5000/ with `adb reverse tcp:5000 tcp:5000`).
    const val BASE_URL = "https://gaming-addiction-api.onrender.com/"

    // SharedPreferences keys
    const val PREFS_NAME = "parent_app_prefs"
    const val KEY_PARENT_ID = "parent_id"
    const val KEY_PARENT_NAME = "parent_name"
    const val KEY_SERVER_URL = "server_url"
    const val KEY_CHILD_USER_ID = "child_user_id"
    const val KEY_LAST_RISK_LEVEL = "last_risk_level"
    const val KEY_FCM_TOKEN = "fcm_token"
    const val KEY_LAST_ALERT_ID = "last_notified_alert_id"
    const val KEY_AUTH_TOKEN = "auth_token"

    // Notification channels
    const val CHANNEL_ALERTS = "alerts_channel"
    const val CHANNEL_POLLING = "polling_channel"

    // Notification IDs
    const val NOTIF_ALERT = 2001
    const val NOTIF_POLLING = 2002

    // Background alert-polling interval (ms). FCM push is the instant path for high-risk
    // alerts; this poll is the catch-all that also delivers the other alert types
    // (session start, toxicity, offline/tamper). 25 s keeps latency low without hammering
    // the free tier — the endpoint is light (no model inference).
    const val POLL_INTERVAL_MS = 25_000L
}
