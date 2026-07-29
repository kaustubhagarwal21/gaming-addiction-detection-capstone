package com.pes.parentmonitor.util

import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationManagerCompat

object NotificationSupport {
    /** App permission/toggle and the individual channel must both allow delivery. */
    fun canPost(context: Context, channelId: String): Boolean {
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return false
        val channel = context.getSystemService(NotificationManager::class.java)
            .getNotificationChannel(channelId) ?: return false
        return channel.importance != NotificationManager.IMPORTANCE_NONE
    }
}
