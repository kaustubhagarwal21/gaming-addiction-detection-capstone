package com.pes.gamingdetector.services

import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.activities.SessionActivity
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Foreground service that hosts an active gaming session: holds a wake lock,
 * shows the ongoing notification, and runs VoiceRecorderService for voice
 * capture. Behavioural features are computed entirely server-side from session
 * history at prediction time, so the app no longer posts behavioural data.
 */
class GameMonitorService : Service() {
    private var sessionId: Int = -1
    private var gameName: String = ""
    private var serverUrl: String = Constants.BASE_URL
    private lateinit var prefs: PrefsManager
    private var wakeLock: PowerManager.WakeLock? = null
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private var nudgeJob: Job? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        prefs = PrefsManager(this)
        // Fall back to prefs when extras are missing (START_STICKY may redeliver a null intent).
        val extraSession = intent?.getIntExtra("session_id", -1) ?: -1
        sessionId = if (extraSession != -1) extraSession else prefs.activeSessionId
        gameName  = intent?.getStringExtra("game_name").orEmpty().ifEmpty { prefs.activeSessionGame }
        serverUrl = intent?.getStringExtra("server_url") ?: prefs.serverUrl

        acquireWakeLock()
        startForeground(Constants.NOTIF_MONITORING, buildNotification())
        startVoiceService()
        startBreakNudges()
        return START_STICKY
    }

    /** Gentle break reminders during the session. Lives in this service (not the session
        screen) so they fire during real gameplay — when the child is in the game and
        never opens our app, which is the normal auto-detected case. */
    private fun startBreakNudges() {
        if (nudgeJob?.isActive == true) return   // START_STICKY can re-enter onStartCommand
        nudgeJob = scope.launch {
            var sent90 = false
            var sent120 = false
            while (isActive) {
                val start = prefs.activeSessionStart
                if (start > 0L) {
                    val mins = (System.currentTimeMillis() - start) / 60_000
                    if (mins >= 120 && !sent120) {
                        sent120 = true
                        sendBreakNudge("2-Hour Reminder",
                            "2 hours of gaming done! Time to take a proper break and rest your eyes.")
                    } else if (mins >= 90 && !sent90) {
                        sent90 = true
                        sendBreakNudge("90-Minute Check-in",
                            "You've been gaming for 90 minutes. Take a 10-minute break — your brain will thank you!")
                    }
                }
                delay(60_000)
            }
        }
    }

    private fun sendBreakNudge(title: String, message: String) {
        try {
            val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(this).notify(System.currentTimeMillis().toInt() and 0xFFFF, notif)
        } catch (_: SecurityException) { /* notifications not permitted — skip */ }
    }

    private fun acquireWakeLock() {
        // Skip if we already hold one — onStartCommand can fire repeatedly under START_STICKY,
        // and re-acquiring without release leaks held wakelocks (drains battery, blocks doze).
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ChildApp::MonitorLock")
        wakeLock?.acquire(4 * 60 * 60 * 1000L)
    }

    private fun buildNotification() = NotificationCompat.Builder(this, Constants.CHANNEL_MONITORING)
        .setContentTitle("Monitoring: $gameName")
        .setContentText("Session active — tap to return")
        .setSmallIcon(R.drawable.ic_monitor)
        .setOngoing(true)
        .setContentIntent(
            PendingIntent.getActivity(
                this, 0,
                Intent(this, SessionActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
                },
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        )
        .build()

    private fun startVoiceService() {
        val intent = Intent(this, VoiceRecorderService::class.java).apply {
            putExtra("session_id", sessionId)
            putExtra("server_url", serverUrl)
        }
        // Voice capture is best-effort: Android 14+ may refuse a mic foreground
        // service started from the background. Never let that take down monitoring.
        try {
            startService(intent)
        } catch (e: Exception) {
            android.util.Log.w("GameMonitor", "Voice service start skipped: ${e.message}")
        }
    }

    override fun onDestroy() {
        scope.cancel()
        wakeLock?.takeIf { it.isHeld }?.release()
        stopService(Intent(this, VoiceRecorderService::class.java))
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
