package com.pes.gamingdetector.services

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Optional device-administrator. Being an *active* admin blocks casual uninstall (Android
 * makes the user deactivate admin first), and [onDisableRequested] fires the instant a
 * deactivation is attempted --- before it actually happens --- so we can alert the parent
 * while the app is still alive and authenticated. We request no admin policies (no
 * lock/wipe); we only use the uninstall-block + this disable hook.
 */
class AdminReceiver : DeviceAdminReceiver() {

    /** Admin just turned ON. Report it immediately so the parent's "uninstall-protected"
     *  status flips back without waiting for the next ~5-min heartbeat (disabling is
     *  already instant via onDisableRequested, so enabling should feel symmetric).
     *  goAsync() keeps the receiver alive while the background POST runs. */
    override fun onEnabled(context: Context, intent: Intent) {
        try {
            val prefs = PrefsManager(context)
            val uid   = prefs.userId
            val token = prefs.authToken
            if (uid == -1) return
            val pending = goAsync()
            Thread {
                try {
                    postJsonBlocking(prefs.serverUrl, token, "api/child/heartbeat",
                        JSONObject().put("user_id", uid).put("device_admin", 1).toString())
                } finally { pending.finish() }
            }.start()
        } catch (e: Exception) {
            Log.w("AdminReceiver", "admin-enabled report failed: ${e.message}")
        }
    }

    override fun onDisableRequested(context: Context, intent: Intent): CharSequence {
        // CRITICAL TIMING: the user is about to remove monitoring, so the process may be
        // killed seconds from now. A fire-and-forget coroutine (the old approach) usually
        // died before its request left the device, so the parent never heard. Instead we
        // send the tamper alert SYNCHRONOUSLY with a short timeout on a background thread
        // we join briefly — Android is showing the warning string we return below, which
        // holds the screen and buys exactly this moment to get the alert out.
        try {
            val prefs = PrefsManager(context)          // also refreshes the bearer token from disk
            val uid   = prefs.userId
            val token = prefs.authToken
            if (uid != -1) {
                val t = Thread {
                    postJsonBlocking(prefs.serverUrl, token, "api/child/tamper",
                        JSONObject().put("user_id", uid).put("event", "admin_disable").toString())
                }
                t.start()
                t.join(4000)                            // best-effort: wait up to 4s, then proceed
            }
        } catch (e: Exception) {
            Log.w("AdminReceiver", "tamper alert failed: ${e.message}")
        }
        // Shown to the user before they confirm; also buys a moment for the alert to send.
        return "Turning this off stops gaming-wellbeing monitoring — your parent will be notified."
    }

    /** Plain blocking HTTP POST (no Retrofit/coroutines) — safe to run on a short-lived
     *  thread during the admin enable/disable window. The heartbeat watchdog and the
     *  periodic heartbeat's device_admin flag remain the fallbacks. */
    private fun postJsonBlocking(serverUrl: String, token: String?, path: String, body: String) {
        try {
            val base = if (serverUrl.endsWith("/")) serverUrl else "$serverUrl/"
            val conn = (URL(base + path).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 3500
                readTimeout = 3500
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (!token.isNullOrEmpty()) setRequestProperty("Authorization", "Bearer $token")
            }
            conn.outputStream.use { it.write(body.toByteArray()) }
            conn.responseCode                            // forces the request to be sent
            conn.disconnect()
        } catch (e: Exception) {
            Log.w("AdminReceiver", "POST $path failed: ${e.message}")
        }
    }
}
