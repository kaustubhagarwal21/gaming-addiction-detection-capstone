package com.pes.parentmonitor

import android.app.Activity
import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.SessionManager
import java.lang.ref.WeakReference

class ParentApp : Application() {
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

        // Token expired/invalid (401) → stop background sync, clear the session, and
        // return to sign-in. Without this the dashboard would just fail to load with
        // no way back to login. Fires at most once until the next successful login.
        ApiClient.onUnauthorized = { revision ->
            Handler(Looper.getMainLooper()).post {
                // A successful login may have completed after the 401 was observed but
                // before this main-thread task ran. Never clear that newer session.
                if (!ApiClient.isCurrentUnauthorized(revision)) return@post
                SessionManager.logout(this, PrefsManager(this))
                // Android blocks arbitrary background Activity launches. If a screen is
                // currently visible, redirect now; otherwise each protected Activity's
                // auth gate redirects the next time the user returns to the app.
                resumedActivity.get()?.let(AuthNavigation::openLogin)
            }
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
            Constants.CHANNEL_ALERTS_GENERAL,
            "Gaming Alerts",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply { description = "Non-urgent gaming and monitoring alerts" })

        nm.createNotificationChannel(NotificationChannel(
            Constants.CHANNEL_ACTIVITY,
            "Activity Updates",
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = "Informational updates such as gaming session starts" })

        nm.createNotificationChannel(NotificationChannel(
            Constants.CHANNEL_POLLING,
            "Background Sync",
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = "Background data sync from child device" })
    }
}
