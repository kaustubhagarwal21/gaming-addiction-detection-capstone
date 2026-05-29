package com.pes.parentmonitor.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.pes.parentmonitor.util.PrefsManager

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = PrefsManager(context)
        if (!prefs.isLoggedIn() || prefs.childUserId == -1) return

        ContextCompat.startForegroundService(
            context,
            Intent(context, AlertPollingService::class.java).apply {
                putExtra("parent_id", prefs.parentId)
                putExtra("child_user_id", prefs.childUserId)
                putExtra("server_url", prefs.serverUrl)
            }
        )
    }
}
