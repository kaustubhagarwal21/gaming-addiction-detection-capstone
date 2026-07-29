package com.pes.parentmonitor.util

import android.content.Context
import android.content.Intent
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
        prefs.logout()
    }
}
