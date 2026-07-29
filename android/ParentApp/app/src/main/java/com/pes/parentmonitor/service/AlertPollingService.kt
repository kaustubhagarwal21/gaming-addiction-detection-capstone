package com.pes.parentmonitor.service

import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.pes.parentmonitor.R
import com.pes.parentmonitor.activities.AlertsActivity
import com.pes.parentmonitor.api.Alert
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.ApiService
import com.pes.parentmonitor.api.ChildInfo
import com.pes.parentmonitor.util.AlertTriage
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.NotificationRouting
import com.pes.parentmonitor.util.NotificationIdentity
import com.pes.parentmonitor.util.NotificationSupport
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class AlertPollingService : Service() {
    @Volatile private var serverUrl: String = Constants.BASE_URL
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PrefsManager
    @Volatile private var pollStarted = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        prefs = PrefsManager(this)
        if (!prefs.isLoggedIn()) {
            stopSelf(startId)
            return START_NOT_STICKY
        }
        serverUrl = intent?.getStringExtra("server_url") ?: prefs.serverUrl

        startForeground(
            Constants.NOTIF_POLLING,
            NotificationCompat.Builder(this, Constants.CHANNEL_POLLING)
                .setContentTitle("Guardian Active")
                .setContentText("Monitoring your family's gaming activity")
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
            if (!prefs.isLoggedIn()) {
                stopSelf()
                return
            }
            checkForAlerts()
            delay(Constants.POLL_INTERVAL_MS)
        }
    }

    private suspend fun checkForAlerts() {
        val url = serverUrl
        try {
            val api = ApiClient.getInstance(url)
            childrenToPoll(api).forEach { child -> checkChildAlerts(api, child) }
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            // Polling is best-effort; the next interval retries. FCM remains the instant path.
        }
    }

    /** Poll every child authorized by the family token. Falling back to the selected
     * child preserves basic alerting if the roster request itself temporarily fails. */
    private suspend fun childrenToPoll(api: ApiService): List<ChildInfo> {
        val response = try {
            api.getChildren()
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            null
        }
        if (response?.isSuccessful == true && response.body()?.success == true) {
            return response.body()?.children.orEmpty()
        }
        val selected = prefs.childUserId
        return if (selected > 0) {
            listOf(ChildInfo(selected, prefs.childName.ifBlank { "Your child" }, null))
        } else emptyList()
    }

    private suspend fun checkChildAlerts(api: ApiService, child: ChildInfo) {
        val response = try {
            api.getAlerts(child.userId)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            return
        }
        if (!response.isSuccessful || response.body()?.success != true) return

        val newAlerts = AlertTriage.newAlertsSince(
            response.body()?.alerts,
            prefs.lastNotifiedAlertId(child.userId)
        )
        if (newAlerts.isEmpty()) return

        val worst = AlertTriage.worstOf(newAlerts) ?: return
        // Only advance after Android accepted the notification. A disabled app/channel
        // keeps the backlog pending so it can surface once the parent enables alerts.
        if (sendAlertNotification(worst, child, newAlerts.size)) {
            prefs.advanceLastNotifiedAlertId(child.userId, newAlerts.maxOf { it.id })
        }
    }

    private fun sendAlertNotification(alert: Alert, child: ChildInfo, newCount: Int): Boolean {
        val channelId = NotificationRouting.channelFor(alert.type, alert.severity)
        if (!NotificationSupport.canPost(this, channelId)) return false
        // Alert ids are globally unique. The former 31*child+alert arithmetic collided
        // across families (child 1 / alert 32 == child 2 / alert 1), replacing the
        // PendingIntent and sometimes opening the wrong child.
        val requestCode = NotificationIdentity.requestCodeForAlert(alert.id)
        val contentIntent = PendingIntent.getActivity(
            this,
            requestCode,
            Intent(this, AlertsActivity::class.java).apply {
                putExtra(Constants.EXTRA_CHILD_USER_ID, child.userId)
                putExtra(Constants.EXTRA_CHILD_NAME, child.name)
                putExtra(Constants.EXTRA_ALERT_TYPE, alert.type)
                flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, channelId)
            // Batch-aware title ("3 new alerts · Arjun"): the batch collapses to one
            // card by design, but its size must never be hidden from the parent.
            .setContentTitle(AlertTriage.notificationTitle(child.name, newCount))
            .setContentText(alert.message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(alert.message))
            .setSmallIcon(R.drawable.ic_alert)
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .setPriority(NotificationRouting.priorityFor(channelId))
            .build()
        return try {
            val id = NotificationIdentity.notificationIdForAlert(alert.id)
            NotificationManagerCompat.from(this).notify(id, notification)
            true
        } catch (_: SecurityException) {
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
