package com.pes.gamingdetector.services

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.pes.gamingdetector.util.PrefsManager

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = PrefsManager(context)
        if (!prefs.isLoggedIn()) return

        // Always restart passive monitor (screen events + auto-session detection)
        ContextCompat.startForegroundService(
            context,
            Intent(context, PassiveMonitorService::class.java)
        )

        // If a session was active when the phone was rebooted, re-attach to it
        if (prefs.hasActiveSession()) {
            ContextCompat.startForegroundService(
                context,
                Intent(context, GameMonitorService::class.java).apply {
                    putExtra("session_id", prefs.activeSessionId)
                    putExtra("game_name", prefs.activeSessionGame)
                    putExtra("user_id", prefs.userId)
                    putExtra("server_url", prefs.serverUrl)
                }
            )
        }
    }
}
