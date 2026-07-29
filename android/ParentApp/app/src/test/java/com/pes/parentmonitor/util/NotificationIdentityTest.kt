package com.pes.parentmonitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationIdentityTest {
    @Test
    fun `different global alert ids cannot reproduce the old cross-child collision`() {
        // Old formula: 31*1+32 == 31*2+1.
        val first = NotificationIdentity.requestCodeForAlert(32)
        val second = NotificationIdentity.requestCodeForAlert(1)
        assertEquals(32, first)
        assertEquals(1, second)
        assertNotEquals(first, second)
        assertNotEquals(
            NotificationIdentity.notificationIdForAlert(32),
            NotificationIdentity.notificationIdForAlert(1),
        )
    }

    @Test
    fun `alert notifications use a namespace disjoint from service notifications`() {
        listOf(1, 2, 32, Int.MAX_VALUE).forEach { alertId ->
            val notificationId = NotificationIdentity.notificationIdForAlert(alertId)
            assertTrue(notificationId < 0)
            assertNotEquals(Constants.NOTIF_POLLING, notificationId)
            assertNotEquals(Constants.NOTIF_ALERT, notificationId)
        }
        assertTrue(NotificationIdentity.fallbackRequestCode("legacy-message") < 0)
        assertNotEquals(
            Constants.NOTIF_POLLING,
            NotificationIdentity.fallbackNotificationId("legacy-message"),
        )
    }
}
