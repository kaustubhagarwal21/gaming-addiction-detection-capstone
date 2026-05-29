package com.pes.parentmonitor.util

object Constants {
    const val BASE_URL = "http://127.0.0.1:5000/"

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

    // Polling interval (ms)
    const val POLL_INTERVAL_MS = 60_000L
}
