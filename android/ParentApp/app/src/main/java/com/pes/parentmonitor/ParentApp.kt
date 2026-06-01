package com.pes.parentmonitor

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import com.pes.parentmonitor.activities.LoginActivity
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.service.AlertPollingService
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.PrefsManager

class ParentApp : Application() {
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()

        // Token expired/invalid (401) → stop background sync, clear the session, and
        // return to sign-in. Without this the dashboard would just fail to load with
        // no way back to login. Fires at most once until the next successful login.
        ApiClient.onUnauthorized = {
            stopService(Intent(this, AlertPollingService::class.java))
            PrefsManager(this).logout()
            startActivity(
                Intent(this, LoginActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            )
        }
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
