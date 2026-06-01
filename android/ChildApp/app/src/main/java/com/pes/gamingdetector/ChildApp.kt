package com.pes.gamingdetector

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import com.pes.gamingdetector.activities.LoginActivity
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.services.GameMonitorService
import com.pes.gamingdetector.services.PassiveMonitorService
import com.pes.gamingdetector.services.VoiceRecorderService
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager

class ChildApp : Application() {
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()

        // Token expired/invalid (401) → stop all monitoring, clear the session, and
        // bounce to sign-in. Without this the app keeps "monitoring" but every upload
        // silently fails. The token is already dead here, so we don't try to end the
        // server session (that would 401 too). Fires once until the next login.
        ApiClient.onUnauthorized = {
            stopService(Intent(this, PassiveMonitorService::class.java))
            stopService(Intent(this, GameMonitorService::class.java))
            stopService(Intent(this, VoiceRecorderService::class.java))
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
