package com.pes.parentmonitor.service

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.pes.parentmonitor.R
import com.pes.parentmonitor.activities.AlertsActivity
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.NotificationIdentity
import com.pes.parentmonitor.util.NotificationRouting
import com.pes.parentmonitor.util.NotificationSupport
import com.pes.parentmonitor.util.PrefsManager

class ParentFCMService : FirebaseMessagingService() {

    // Called when FCM issues a new registration token for this device.
    override fun onNewToken(token: String) {
        val prefs = PrefsManager(this)
        prefs.fcmToken = token
        if (prefs.isLoggedIn()) {
            FcmTokenSyncWorker.enqueueRegistration(this, token)
        }
    }

    // Backend pushes are data-only so this code controls routing in both foreground and
    // background. A logged-out device may still receive a push while durable unregister
    // is waiting for connectivity; never show it locally.
    override fun onMessageReceived(message: RemoteMessage) {
        val prefs = PrefsManager(this)
        if (!prefs.isLoggedIn()) return
        if (!NotificationRouting.belongsToFamily(
                message.data["family_code"],
                prefs.familyCode
            )
        ) return

        val childId = message.data["child_id"]?.toIntOrNull()
        val childName = message.data["child_name"]?.takeIf { it.isNotBlank() }
        val title = message.data["title"]?.takeIf { it.isNotBlank() }
            ?: message.notification?.title ?: "Parental Alert"
        val body = message.data["body"]?.takeIf { it.isNotBlank() }
            ?: message.notification?.body ?: "Check your child's gaming activity"
        showNotification(
            title = title,
            body = body,
            childId = childId,
            childName = childName,
            alertType = message.data["type"],
            severity = message.data["severity"],
            alertId = message.data["alert_id"]?.toIntOrNull(),
            notificationKey = message.messageId
        )
    }

    private fun showNotification(
        title: String,
        body: String,
        childId: Int?,
        childName: String?,
        alertType: String?,
        severity: String?,
        alertId: Int?,
        notificationKey: String?
    ) {
        val prefs = PrefsManager(this)
        if (childId != null && childId > 0 && alertId != null && alertId > 0 &&
            alertId <= prefs.lastNotifiedAlertId(childId)
        ) return
        val channelId = NotificationRouting.channelFor(alertType, severity)
        if (!NotificationSupport.canPost(this, channelId)) return
        val intent = Intent(this, AlertsActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            childId?.takeIf { it > 0 }?.let { putExtra(Constants.EXTRA_CHILD_USER_ID, it) }
            childName?.let { putExtra(Constants.EXTRA_CHILD_NAME, it) }
            alertType?.let { putExtra(Constants.EXTRA_ALERT_TYPE, it) }
        }
        val durableAlertId = alertId?.takeIf { it > 0 }
        val requestCode = durableAlertId?.let(NotificationIdentity::requestCodeForAlert)
            ?: NotificationIdentity.fallbackRequestCode(
                notificationKey ?: "${childId ?: "unknown"}:$body"
            )
        val pi = PendingIntent.getActivity(
            this, requestCode, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val notif = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.drawable.ic_alert)
            .setContentTitle(childName?.let { "$title · $it" } ?: title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationRouting.priorityFor(channelId))
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        try {
            val notificationId = durableAlertId?.let(NotificationIdentity::notificationIdForAlert)
                ?: NotificationIdentity.fallbackNotificationId(
                    notificationKey ?: "${childId ?: "unknown"}:$body"
                )
            getSystemService(NotificationManager::class.java)
                .notify(notificationId, notif)
            if (childId != null && childId > 0 && alertId != null &&
                alertId > prefs.lastNotifiedAlertId(childId)
            ) {
                prefs.advanceLastNotifiedAlertId(childId, alertId)
            }
        } catch (_: SecurityException) { /* permission was revoked after the check */ }
    }
}
