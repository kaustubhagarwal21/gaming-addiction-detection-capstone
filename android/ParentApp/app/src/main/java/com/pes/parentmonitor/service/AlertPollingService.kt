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
    private var childUserId: Int = -1
    private var serverUrl: String = Constants.BASE_URL
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PrefsManager

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        prefs = PrefsManager(this)
        // Fall back to prefs when extras are missing (e.g. START_STICKY redelivery
        // gives a null intent). Without this, childUserId becomes -1 and polling
        // silently no-ops forever.
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

        scope.launch { pollLoop() }
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
                // Only notify for alerts newer than the last one we already showed
                val lastId  = prefs.lastNotifiedAlertId
                val newAlerts = body.alerts
                    ?.filter { !it.read && it.id > lastId }
                    ?.sortedBy { it.id }
                    ?: emptyList()
                if (newAlerts.isNotEmpty()) {
                    val worst = newAlerts.maxByOrNull { severityRank(it.severity) }!!
                    sendAlertNotification(worst.message, worst.severity)
                    prefs.lastNotifiedAlertId = newAlerts.last().id
                }

                val statusResp = api.getChildStatus(childUserId)
                if (statusResp.isSuccessful && statusResp.body()?.success == true) {
                    val status = statusResp.body()!!
                    val newRisk = status.currentRisk ?: ""
                    if (newRisk.isNotEmpty() && newRisk != prefs.lastRiskLevel) {
                        if (newRisk.lowercase() in listOf("at_risk", "addicted")) {
                            sendRiskChangeNotification(newRisk, status.currentGame)
                        }
                        prefs.lastRiskLevel = newRisk
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

    private fun sendAlertNotification(message: String, severity: String) {
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

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            NotificationManagerCompat.from(this).notify(Constants.NOTIF_ALERT, notif)
        }
    }

    private fun sendRiskChangeNotification(risk: String, game: String?) {
        val gameStr = if (game != null) " while playing $game" else ""
        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
            .setContentTitle("Risk Level Changed")
            .setContentText("Child is now ${risk.uppercase()}$gameStr")
            .setSmallIcon(R.drawable.ic_alert)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        // Android 13+ requires POST_NOTIFICATIONS at runtime; without it notify() is a
        // no-op (and lint-flagged). Guard inline so a denied permission never surfaces as
        // an error. (On API < 33 checkSelfPermission returns granted automatically.)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            NotificationManagerCompat.from(this).notify(Constants.NOTIF_ALERT + 1, notif)
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
