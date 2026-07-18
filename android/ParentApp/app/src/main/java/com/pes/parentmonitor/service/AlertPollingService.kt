package com.pes.parentmonitor.service

import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.pes.parentmonitor.R
import com.pes.parentmonitor.activities.AlertsActivity
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.util.AlertTriage
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.RiskPresentation
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
    // Which alerts/levels notify, and when, is decided by AlertTriage (pure, unit-tested).
    private val riskNotifiedAt = HashMap<String, Long>()

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
        // Snapshot the target child ONCE. childUserId is @Volatile and can change mid-poll
        // ("switch child" re-invokes onStartCommand); reading it again after each await let
        // one child's alert id be saved as another child's high-water mark, suppressing the
        // second child's alerts. Everything in this pass is keyed off `child`, and a fetch
        // that finishes after a switch is discarded.
        val child = childUserId
        if (child == -1) return
        try {
            val api = ApiClient.getInstance(serverUrl)
            val resp = api.getAlerts(child)
            if (child != childUserId) return   // switched mid-flight — drop this result
            if (resp.isSuccessful && resp.body()?.success == true) {
                val body = resp.body()!!
                // Only notify for alerts newer than the last one we already showed FOR
                // THIS CHILD. Alert ids are globally unique, so a single shared high-water
                // mark suppressed a sibling's older-id alerts after viewing another child
                // — the mark is now kept per child.
                val lastId  = prefs.lastNotifiedAlertId(child)
                val newAlerts = AlertTriage.newAlertsSince(body.alerts, lastId)
                if (newAlerts.isNotEmpty()) {
                    val worst = AlertTriage.worstOf(newAlerts)!!
                    // Only advance the high-water mark if the notification was actually
                    // shown. If POST_NOTIFICATIONS is denied, leave it so the backlog
                    // surfaces once the parent grants permission (instead of being lost).
                    if (sendAlertNotification(worst.message, worst.severity)) {
                        prefs.setLastNotifiedAlertId(child, newAlerts.last().id)
                    }
                }

                val statusResp = api.getChildStatus(child)
                if (child != childUserId) return   // switched mid-flight — drop this result
                if (statusResp.isSuccessful && statusResp.body()?.success == true) {
                    val status = statusResp.body()!!
                    val newRisk = status.currentRisk ?: ""
                    if (newRisk.isNotEmpty() && newRisk != prefs.lastRiskLevel(child)) {
                        val worthy = AlertTriage.isNotifyWorthyRisk(newRisk)
                        val now = System.currentTimeMillis()
                        // Cooldown is per child+level: keyed by child so siblings don't share it.
                        val key = "$child:$newRisk"
                        if (worthy && AlertTriage.riskCooldownPassed(riskNotifiedAt[key] ?: 0L, now)) {
                            if (sendRiskChangeNotification(newRisk, status.currentGame)) {
                                riskNotifiedAt[key] = now
                                prefs.setLastRiskLevel(child, newRisk)
                            }
                            // not shown (permission denied) → don't advance; retry next poll
                        } else {
                            // not notify-worthy, or within cooldown → consider it handled
                            prefs.setLastRiskLevel(child, newRisk)
                        }
                    }
                }
            }
        } catch (_: Exception) {}
    }

    /** Can a notification actually be posted right now? areNotificationsEnabled() is
     *  correct on EVERY Android version: on 13+ it reflects the POST_NOTIFICATIONS
     *  runtime permission, and on 8–12 it reflects the app's notification toggle.
     *  (A raw checkSelfPermission(POST_NOTIFICATIONS) is always DENIED below 13 —
     *  the permission doesn't exist there — which silently suppressed all polling
     *  notifications on older devices.) */
    private fun canNotify(): Boolean =
        NotificationManagerCompat.from(this).areNotificationsEnabled()

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
        // try/catch as well as the canNotify() pre-check: the permission can be revoked
        // between check and notify, and a false return correctly leaves the high-water
        // mark unadvanced so the alert is retried on a later poll.
        return try {
            NotificationManagerCompat.from(this).notify(Constants.NOTIF_ALERT, notif)
            true
        } catch (_: SecurityException) {
            false
        }
    }

    private fun sendRiskChangeNotification(risk: String, game: String?): Boolean {
        if (!canNotify()) return false
        val gameStr = if (game != null) " while playing $game" else ""
        val label = RiskPresentation.displayLabel(risk, null)
        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
            .setContentTitle("Session concern changed")
            .setContentText("Latest session: $label$gameStr")
            .setSmallIcon(R.drawable.ic_alert)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        return try {
            NotificationManagerCompat.from(this).notify(Constants.NOTIF_ALERT + 1, notif)
            true
        } catch (_: SecurityException) {   // revoked between check and notify
            false
        }
    }

    override fun onDestroy() {
        scope.cancel()
        pollStarted = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
