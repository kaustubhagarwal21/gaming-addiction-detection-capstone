package com.pes.parentmonitor.util

import com.pes.parentmonitor.api.Alert

/** Backward-compatible unread total for dashboard badges. */
object AlertCounts {
    fun unread(serverTotal: Int?, embeddedAlerts: List<Alert>?): Int =
        serverTotal?.takeIf { it >= 0 }
            ?: embeddedAlerts.orEmpty().count { !it.read }
}
