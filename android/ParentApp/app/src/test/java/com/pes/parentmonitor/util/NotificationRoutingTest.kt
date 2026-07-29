package com.pes.parentmonitor.util

import androidx.core.app.NotificationCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationRoutingTest {
    @Test
    fun `session start and informational events never use urgent channel`() {
        assertEquals(
            Constants.CHANNEL_ACTIVITY,
            NotificationRouting.channelFor("session_start", "high")
        )
        assertEquals(
            Constants.CHANNEL_ACTIVITY,
            NotificationRouting.channelFor("login", "info")
        )
        assertEquals(
            Constants.CHANNEL_ACTIVITY,
            NotificationRouting.channelFor("other", "low")
        )
    }

    @Test
    fun `high risk routes urgently and medium routes normally`() {
        assertEquals(
            Constants.CHANNEL_ALERTS,
            NotificationRouting.channelFor("risk", "high")
        )
        assertEquals(
            Constants.CHANNEL_ALERTS,
            NotificationRouting.channelFor("monitoring-alert", null)
        )
        assertEquals(
            Constants.CHANNEL_ALERTS_GENERAL,
            NotificationRouting.channelFor("toxicity", "medium")
        )
        assertEquals(
            NotificationCompat.PRIORITY_DEFAULT,
            NotificationRouting.priorityFor(Constants.CHANNEL_ALERTS_GENERAL)
        )
    }

    @Test
    fun `push family binding fails closed and normalizes case`() {
        assertTrue(NotificationRouting.belongsToFamily(" fam123 ", "FAM123"))
        assertFalse(NotificationRouting.belongsToFamily("OTHER", "FAM123"))
        assertFalse(NotificationRouting.belongsToFamily(null, "FAM123"))
        assertFalse(NotificationRouting.belongsToFamily("FAM123", ""))
    }
}
