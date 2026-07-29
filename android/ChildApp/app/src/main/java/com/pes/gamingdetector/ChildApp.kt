package com.pes.gamingdetector

import android.app.Activity
import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.services.GameMonitorService
import com.pes.gamingdetector.services.PassiveMonitorService
import com.pes.gamingdetector.services.VoiceRecorderService
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.AuthNavigation
import com.pes.gamingdetector.util.PrefsManager
import java.lang.ref.WeakReference

class ChildApp : Application() {
    private var resumedActivity = WeakReference<Activity>(null)

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()

        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                resumedActivity = WeakReference(activity)
            }

            override fun onActivityPaused(activity: Activity) {
                if (resumedActivity.get() === activity) resumedActivity.clear()
            }

            override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, state: Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) = Unit
        })

        // Token expired/invalid (401) → stop all monitoring, clear the session, and
        // bounce to sign-in. Without this the app keeps "monitoring" but every upload
        // silently fails. The token is already dead here, so we don't try to end the
        // server session (that would 401 too). Fires once until the next login.
        ApiClient.onUnauthorized = { revision ->
            // Interceptors run on OkHttp threads. Service/activity lifecycle operations
            // belong on the main thread, and background activity-launch restrictions are
            // less error-prone when an already-visible task is being cleared from there.
            Handler(Looper.getMainLooper()).post {
                // A login may have completed while this callback crossed threads.
                if (!ApiClient.isCurrentUnauthorized(revision)) return@post
                stopService(Intent(this, PassiveMonitorService::class.java))
                stopService(Intent(this, GameMonitorService::class.java))
                stopService(Intent(this, VoiceRecorderService::class.java))
                PrefsManager(this).logout()
                // Background Activity launches are restricted. Redirect immediately only
                // when our task is visible; otherwise the protected Activity resume gate
                // opens Login the next time the child returns from Recents.
                resumedActivity.get()?.let(AuthNavigation::openLogin)
            }
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
