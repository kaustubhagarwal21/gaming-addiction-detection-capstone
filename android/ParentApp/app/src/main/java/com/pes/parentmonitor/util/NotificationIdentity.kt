package com.pes.parentmonitor.util

/**
 * Stable Android identities for a durable backend alert.
 *
 * Alert ids are globally unique, so they are already the correct PendingIntent
 * identity. Notification ids are mapped bijectively into the negative Int namespace;
 * app service notifications use small positive ids (for example NOTIF_POLLING=2002),
 * so an alert can never replace the foreground-service card.
 */
object NotificationIdentity {
    fun requestCodeForAlert(alertId: Int): Int {
        require(alertId > 0) { "alertId must be positive" }
        return alertId
    }

    fun notificationIdForAlert(alertId: Int): Int {
        require(alertId > 0) { "alertId must be positive" }
        return alertId xor Int.MIN_VALUE
    }

    /** Keep id-less legacy PendingIntents separate from positive durable alert ids. */
    fun fallbackRequestCode(key: String): Int =
        key.hashCode() or Int.MIN_VALUE

    /**
     * Id-less legacy pushes use the positive namespace. Avoid the two app-reserved
     * service constants explicitly; durable alerts occupy the disjoint negative side.
     */
    fun fallbackNotificationId(key: String): Int {
        val candidate = key.hashCode() and Int.MAX_VALUE
        return if (candidate == Constants.NOTIF_ALERT || candidate == Constants.NOTIF_POLLING) {
            candidate xor 0x40000000
        } else {
            candidate
        }
    }
}
