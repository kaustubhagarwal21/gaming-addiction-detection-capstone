package com.pes.parentmonitor.util

import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat
import com.pes.parentmonitor.service.AlertPollingService
import com.pes.parentmonitor.service.FcmTokenSyncWorker

object SessionManager {
    /** Queue push-token removal before clearing encrypted session state. */
    fun logout(context: Context, prefs: PrefsManager = PrefsManager(context)) {
        val token = prefs.fcmToken
        val serverUrl = prefs.serverUrl
        if (token.isNotBlank()) {
            FcmTokenSyncWorker.enqueueUnregistration(context, serverUrl, token)
        }
        context.stopService(Intent(context, AlertPollingService::class.java))
        // Posted alert cards outlive the session that produced them. Each carries a
        // PendingIntent naming a specific child, so tapping a leftover card after a
        // DIFFERENT family signs in on this device would silently retarget the app to
        // the previous family's child id (the server then 403s, leaving a confusing
        // broken state). They also expose the previous family's alert text on the
        // lock screen. Clear them with the session.
        runCatching {
            NotificationManagerCompat.from(context).cancelAll()
        }
        prefs.logout()
    }
}
