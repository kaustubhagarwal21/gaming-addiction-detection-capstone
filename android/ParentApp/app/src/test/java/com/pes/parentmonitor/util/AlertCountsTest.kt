package com.pes.parentmonitor.util

import com.pes.parentmonitor.api.Alert
import org.junit.Assert.assertEquals
import org.junit.Test

class AlertCountsTest {
    private fun alert(id: Int, read: Boolean) = Alert(
        id = id,
        type = "risk",
        message = "m",
        severity = "medium",
        createdAt = "2026-07-29T00:00:00",
        read = read
    )

    @Test
    fun `server total includes unread rows outside embedded dashboard page`() {
        val embedded = listOf(alert(1, read = false), alert(2, read = true))
        assertEquals(9, AlertCounts.unread(serverTotal = 9, embeddedAlerts = embedded))
    }

    @Test
    fun `old or invalid server total falls back to embedded rows`() {
        val embedded = listOf(alert(1, read = false), alert(2, read = true))
        assertEquals(1, AlertCounts.unread(serverTotal = null, embeddedAlerts = embedded))
        assertEquals(1, AlertCounts.unread(serverTotal = -1, embeddedAlerts = embedded))
    }
}
