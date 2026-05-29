package com.pes.gamingdetector

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.pes.gamingdetector.util.Constants

class ChildApp : Application() {
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val nm = getSystemService(NotificationManager::class.java)

        nm.createNotificationChannel(NotificationChannel(
            Constants.CHANNEL_MONITORING,
            "Session Monitoring",
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = "Active gaming session monitoring" })

        nm.createNotificationChannel(NotificationChannel(
            Constants.CHANNEL_ALERTS,
            "Risk Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply { description = "Gaming risk level alerts" })
    }
}
