package com.pes.parentmonitor

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.pes.parentmonitor.util.Constants

class ParentApp : Application() {
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val nm = getSystemService(NotificationManager::class.java)

        nm.createNotificationChannel(NotificationChannel(
            Constants.CHANNEL_ALERTS,
            "Child Risk Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply { description = "Alerts when child's gaming risk level changes" })

        nm.createNotificationChannel(NotificationChannel(
            Constants.CHANNEL_POLLING,
            "Background Sync",
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = "Background data sync from child device" })
    }
}
