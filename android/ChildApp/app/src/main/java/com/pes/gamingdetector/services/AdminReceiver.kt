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
                    postTamperBlocking(prefs.serverUrl, token, uid, "admin_disable")
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
     *  thread during the disable window. The heartbeat watchdog remains the fallback. */
    private fun postTamperBlocking(serverUrl: String, token: String?, uid: Int, event: String) {
        try {
            val base = if (serverUrl.endsWith("/")) serverUrl else "$serverUrl/"
            val conn = (URL(base + "api/child/tamper").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 3500
                readTimeout = 3500
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (!token.isNullOrEmpty()) setRequestProperty("Authorization", "Bearer $token")
            }
            val body = JSONObject().put("user_id", uid).put("event", event).toString()
            conn.outputStream.use { it.write(body.toByteArray()) }
            conn.responseCode                            // forces the request to be sent
            conn.disconnect()
        } catch (e: Exception) {
            Log.w("AdminReceiver", "tamper POST failed: ${e.message}")
        }
    }
}
