package com.pes.parentmonitor.util

import androidx.core.app.NotificationCompat

/** Pure notification routing so informational events never inherit alert-channel urgency. */
object NotificationRouting {
    private val activityTypes = setOf(
        "session_start", "session_started", "login", "activity", "info"
    )
    private val timeCriticalTypes = setOf(
        "risk_alert", "monitoring_alert", "tamper", "offline"
    )

    fun channelFor(type: String?, severity: String?): String {
        val normalizedType = normalize(type)
        val normalizedSeverity = normalize(severity)
        return when {
            // Event meaning wins over a malformed severity supplied by an older server.
            normalizedType in activityTypes -> Constants.CHANNEL_ACTIVITY
            normalizedSeverity == "high" || normalizedType in timeCriticalTypes ->
                Constants.CHANNEL_ALERTS
            normalizedSeverity in setOf("info", "low") -> Constants.CHANNEL_ACTIVITY
            else -> Constants.CHANNEL_ALERTS_GENERAL
        }
    }

    fun priorityFor(channelId: String): Int = when (channelId) {
        Constants.CHANNEL_ALERTS -> NotificationCompat.PRIORITY_HIGH
        Constants.CHANNEL_ACTIVITY -> NotificationCompat.PRIORITY_LOW
        else -> NotificationCompat.PRIORITY_DEFAULT
    }

    /**
     * Accept data-only FCM messages only for the family of the current login.
     * Missing bindings fail closed; authenticated polling remains the fallback.
     */
    fun belongsToFamily(incoming: String?, current: String?): Boolean {
        val expected = current?.trim()?.uppercase().orEmpty()
        val received = incoming?.trim()?.uppercase().orEmpty()
        return expected.isNotEmpty() && received == expected
    }

    private fun normalize(value: String?): String =
        value?.trim()?.lowercase()?.replace('-', '_').orEmpty()
}
