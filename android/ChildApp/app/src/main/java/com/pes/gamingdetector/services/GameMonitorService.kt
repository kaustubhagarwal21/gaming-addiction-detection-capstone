package com.pes.gamingdetector.services

import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.activities.SessionActivity
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.SessionDurationClock
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
    companion object {
        // Break/limit nudge notification ids, namespaced (like the parent-nudge ids in
        // PassiveMonitorService) well away from the small positive foreground-service
        // ids so a nudge can never replace an ongoing service notification.
        private const val NOTIF_BREAK_90      = 0x42000001
        private const val NOTIF_BREAK_120     = 0x42000002
        private const val NOTIF_LIMIT_REACHED = 0x42000003
    }

    private var sessionId: Int = -1
    private var gameName: String = ""
    private var serverUrl: String = Constants.BASE_URL
    private lateinit var prefs: PrefsManager
    private var wakeLock: PowerManager.WakeLock? = null
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private var nudgeJob: Job? = null
    private var durationClockSessionId = -1
    private var durationClock: SessionDurationClock? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        prefs = PrefsManager(this)
        // Fall back to prefs when extras are missing (START_STICKY may redeliver a null intent).
        val extraSession = intent?.getIntExtra("session_id", -1) ?: -1
        sessionId = if (extraSession != -1) extraSession else prefs.activeSessionId
        gameName  = intent?.getStringExtra("game_name").orEmpty().ifEmpty { prefs.activeSessionGame }
        serverUrl = intent?.getStringExtra("server_url") ?: prefs.serverUrl

        startForeground(Constants.NOTIF_MONITORING, buildNotification())
        // A sticky restart can arrive after logout, consent expiry, or a successful end.
        // Promote immediately to satisfy the 5-second contract, then fail closed.
        if (!prefs.canMonitor() || sessionId <= 0 || sessionId != prefs.activeSessionId) {
            stopSelf()
            return START_NOT_STICKY
        }
        acquireWakeLock()
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
            var limitNotified = false
            while (isActive) {
                val start = prefs.activeSessionStart
                if (start > 0L) {
                    val mins = currentSessionElapsedMs(start) / 60_000
                    if (mins >= 120 && !sent120) {
                        sent120 = true
                        // A service restarted after two hours must not send the older
                        // 90-minute reminder one minute after the 2-hour reminder.
                        sent90 = true
                        sendBreakNudge(NOTIF_BREAK_120, "2-Hour Reminder",
                            "2 hours of gaming done! Time to take a proper break and rest your eyes.")
                    } else if (mins >= 90 && !sent90) {
                        sent90 = true
                        sendBreakNudge(NOTIF_BREAK_90, "90-Minute Check-in",
                            "You've been gaming for 90 minutes. Take a 10-minute break — your brain will thank you!")
                    }
                    // Parent-set daily limit reached for today (completed sessions + this one).
                    if (!limitNotified) {
                        val limit = checkDailyLimitReached(start)
                        if (limit != null) {
                            limitNotified = true
                            sendBreakNudge(NOTIF_LIMIT_REACHED, "Daily limit reached",
                                "You've hit your ${"%.1f".format(limit)}h gaming limit for today. " +
                                "Time to wrap up and do something else — your parent set this with you. 🌟")
                        }
                    }
                }
                delay(60_000)
            }
        }
    }

    /** Today's total play time (completed sessions + the live one) vs the parent's daily
        limit. Returns the limit hours if reached/exceeded, else null. Only fires when a
        parent actually set a limit — never for the soft default goal. */
    private suspend fun checkDailyLimitReached(sessionStart: Long): Double? = try {
        val resp = ApiClient.getInstance(serverUrl).getChildEnriched(prefs.userId)
        val b = resp.body()
        val limit = b?.dailyGoalHours
        if (resp.isSuccessful && b?.success == true && b.goalIsParentSet == true && limit != null) {
            val sessionHrs = currentSessionElapsedMs(sessionStart) / 3_600_000.0
            val totalToday = (b.playedTodayHours ?: 0.0) + sessionHrs
            if (totalToday >= limit) limit else null
        } else null
    } catch (_: Exception) { null }

    private fun currentSessionElapsedMs(sessionStartEpochMs: Long): Long {
        if (durationClock == null || durationClockSessionId != sessionId) {
            durationClockSessionId = sessionId
            durationClock = SessionDurationClock(
                sessionStartedAtEpochMs = sessionStartEpochMs,
                createdAtEpochMs = System.currentTimeMillis(),
                createdAtElapsedMs = SystemClock.elapsedRealtime(),
            )
        }
        return durationClock!!.elapsedMs(SystemClock.elapsedRealtime())
    }

    private fun sendBreakNudge(notificationId: Int, title: String, message: String) {
        try {
            val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .build()
            // Stable id per nudge kind. The old random 16-bit id (millis and 0xFFFF)
            // could land on a reserved foreground-service id (1001 monitoring, 1011
            // voice, 1099 passive monitor, ...) and replace that ongoing card with an
            // auto-cancel nudge. Same-kind replacement is fine — the newer text wins.
            NotificationManagerCompat.from(this).notify(notificationId, notif)
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
        // Until VoiceRecorder proves the whole record+upload path is working, expose
        // it as unavailable rather than retaining a stale "active" value.
        prefs.voiceCaptureActive = false
        val intent = Intent(this, VoiceRecorderService::class.java).apply {
            putExtra("session_id", sessionId)
            putExtra("server_url", serverUrl)
        }
        // Voice capture is best-effort: Android 14+ may refuse a mic foreground
        // service started from the background. Never let that take down monitoring.
        try {
            androidx.core.content.ContextCompat.startForegroundService(this, intent)
        } catch (e: Exception) {
            prefs.voiceCaptureActive = false
            android.util.Log.w("GameMonitor", "Voice service start skipped: ${e.message}")
        }
    }

    override fun onDestroy() {
        scope.cancel()
        wakeLock?.takeIf { it.isHeld }?.release()
        // Ask voice capture to close the recorder and drain its bounded final segment.
        // Unauthorized/logout paths still stop VoiceRecorderService directly for privacy.
        try {
            startService(
                Intent(this, VoiceRecorderService::class.java)
                    .setAction(VoiceRecorderService.ACTION_STOP)
            )
        } catch (_: Exception) {
            stopService(Intent(this, VoiceRecorderService::class.java))
        }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
