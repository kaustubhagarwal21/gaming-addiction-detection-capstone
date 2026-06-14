package com.pes.parentmonitor.service

import android.Manifest
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.pes.parentmonitor.R
import com.pes.parentmonitor.activities.AlertsActivity
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.*

class AlertPollingService : Service() {
    private var parentId: Int = -1
    @Volatile private var childUserId: Int = -1
    private var serverUrl: String = Constants.BASE_URL
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PrefsManager
    // onStartCommand re-fires every time the dashboard opens (and on STICKY redelivery);
    // only ONE poll loop must run — duplicates would double every notification.
    @Volatile private var pollStarted = false
    // Last time each risk level was notified (in-memory; resets with the service).
    private val riskNotifiedAt = HashMap<String, Long>()
    private val RISK_RENOTIFY_MS = 30 * 60 * 1000L

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        prefs = PrefsManager(this)
        // Fall back to prefs when extras are missing (e.g. START_STICKY redelivery
        // gives a null intent). Without this, childUserId becomes -1 and polling
        // silently no-ops forever. Fields are ALWAYS refreshed (even when the loop is
        // already running) so a repeat start after "switch child" re-targets polling.
        val extraParent = intent?.getIntExtra("parent_id", -1) ?: -1
        val extraChild  = intent?.getIntExtra("child_user_id", -1) ?: -1
        parentId    = if (extraParent != -1) extraParent else prefs.parentId
        childUserId = if (extraChild  != -1) extraChild  else prefs.childUserId
        serverUrl   = intent?.getStringExtra("server_url") ?: prefs.serverUrl

        startForeground(
            Constants.NOTIF_POLLING,
            NotificationCompat.Builder(this, Constants.CHANNEL_POLLING)
                .setContentTitle("Guardian Active")
                .setContentText("Monitoring child's gaming activity")
                .setSmallIcon(R.drawable.ic_shield)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build()
        )

        if (!pollStarted) {
            pollStarted = true
            scope.launch { pollLoop() }
        }
        return START_STICKY
    }

    private suspend fun pollLoop() {
        while (currentCoroutineContext().isActive) {
            checkForAlerts()
            delay(Constants.POLL_INTERVAL_MS)
        }
    }

    private suspend fun checkForAlerts() {
        if (childUserId == -1) return
        try {
            val api = ApiClient.getInstance(serverUrl)
            val resp = api.getAlerts(childUserId)
            if (resp.isSuccessful && resp.body()?.success == true) {
                val body = resp.body()!!
                // Only notify for alerts newer than the last one we already showed FOR
                // THIS CHILD. Alert ids are globally unique, so a single shared high-water
                // mark suppressed a sibling's older-id alerts after viewing another child
                // — the mark is now kept per child.
                val lastId  = prefs.lastNotifiedAlertId(childUserId)
                val newAlerts = body.alerts
                    ?.filter { !it.read && it.id > lastId }
                    ?.sortedBy { it.id }
                    ?: emptyList()
                if (newAlerts.isNotEmpty()) {
                    val worst = newAlerts.maxByOrNull { severityRank(it.severity) }!!
                    // Only advance the high-water mark if the notification was actually
                    // shown. If POST_NOTIFICATIONS is denied, leave it so the backlog
                    // surfaces once the parent grants permission (instead of being lost).
                    if (sendAlertNotification(worst.message, worst.severity)) {
                        prefs.setLastNotifiedAlertId(childUserId, newAlerts.last().id)
                    }
                }

                val statusResp = api.getChildStatus(childUserId)
                if (statusResp.isSuccessful && statusResp.body()?.success == true) {
                    val status = statusResp.body()!!
                    val newRisk = status.currentRisk ?: ""
                    if (newRisk.isNotEmpty() && newRisk != prefs.lastRiskLevel(childUserId)) {
                        val worthy = newRisk.lowercase() in listOf("at_risk", "addicted")
                        val now = System.currentTimeMillis()
                        // Cooldown is per child+level: consecutive sessions either side of a
                        // band cut-off flip the level back and forth, and one alert per level
                        // per window is plenty. Keyed by child so siblings don't share it.
                        val key = "$childUserId:$newRisk"
                        if (worthy && now - (riskNotifiedAt[key] ?: 0L) > RISK_RENOTIFY_MS) {
                            if (sendRiskChangeNotification(newRisk, status.currentGame)) {
                                riskNotifiedAt[key] = now
                                prefs.setLastRiskLevel(childUserId, newRisk)
                            }
                            // not shown (permission denied) → don't advance; retry next poll
                        } else {
                            // not notify-worthy, or within cooldown → consider it handled
                            prefs.setLastRiskLevel(childUserId, newRisk)
                        }
                    }
                }
            }
        } catch (_: Exception) {}
    }

    private fun severityRank(s: String): Int = when (s.lowercase()) {
        "high"   -> 3
        "medium" -> 2
        "low"    -> 1
        else     -> 0
    }

    /** Returns true only if the notification was actually posted (POST_NOTIFICATIONS
     *  granted), so the caller knows whether to advance its "already notified" marker. */
    private fun canNotify(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun sendAlertNotification(message: String, severity: String): Boolean {
        if (!canNotify()) return false
        val intent = PendingIntent.getActivity(
            this, 0,
            Intent(this, AlertsActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
            .setContentTitle("⚠️ Gaming Alert")
            .setContentText(message)
            .setSmallIcon(R.drawable.ic_alert)
            .setContentIntent(intent)
            .setAutoCancel(true)
            .setPriority(if (severity.lowercase() == "high") NotificationCompat.PRIORITY_HIGH
                else NotificationCompat.PRIORITY_DEFAULT)
            .build()
        NotificationManagerCompat.from(this).notify(Constants.NOTIF_ALERT, notif)
        return true
    }

    private fun sendRiskChangeNotification(risk: String, game: String?): Boolean {
        if (!canNotify()) return false
        val gameStr = if (game != null) " while playing $game" else ""
        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
            .setContentTitle("Risk Level Changed")
            .setContentText("Child is now ${risk.uppercase()}$gameStr")
            .setSmallIcon(R.drawable.ic_alert)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        NotificationManagerCompat.from(this).notify(Constants.NOTIF_ALERT + 1, notif)
        return true
    }

    override fun onDestroy() {
        scope.cancel()
        pollStarted = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
