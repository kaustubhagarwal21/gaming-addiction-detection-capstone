package com.pes.gamingdetector.services

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Optional device-administrator. Being an *active* admin blocks casual uninstall (Android
 * makes the user deactivate admin first), and [onDisableRequested] fires the instant a
 * deactivation is attempted --- before it actually happens --- so we can alert the parent
 * while the app is still alive and authenticated. We request no admin policies (no
 * lock/wipe); we only use the uninstall-block + this disable hook.
 */
class AdminReceiver : DeviceAdminReceiver() {

    override fun onDisableRequested(context: Context, intent: Intent): CharSequence {
        // Best-effort instant tamper alert to the parent, fired before admin is removed.
        try {
            val prefs = PrefsManager(context)          // also refreshes the bearer token from disk
            val uid = prefs.userId
            if (uid != -1) {
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        ApiClient.getInstance(prefs.serverUrl)
                            .reportTamper(mapOf("user_id" to uid, "event" to "admin_disable"))
                    } catch (_: Exception) { /* heartbeat watchdog is the fallback */ }
                }
            }
        } catch (_: Exception) {}
        // Shown to the user before they confirm; also buys a moment for the alert to send.
        return "Turning this off stops gaming-wellbeing monitoring — your parent will be notified."
    }
}
