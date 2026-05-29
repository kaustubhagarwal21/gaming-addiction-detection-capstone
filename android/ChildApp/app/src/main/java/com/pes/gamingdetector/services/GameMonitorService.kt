package com.pes.gamingdetector.services

import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.activities.SessionActivity
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager

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
        return START_STICKY
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
        startService(intent)
    }

    override fun onDestroy() {
        wakeLock?.takeIf { it.isHeld }?.release()
        stopService(Intent(this, VoiceRecorderService::class.java))
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
