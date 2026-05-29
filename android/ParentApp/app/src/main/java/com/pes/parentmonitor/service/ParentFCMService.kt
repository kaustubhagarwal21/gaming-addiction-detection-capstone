package com.pes.parentmonitor.service

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.pes.parentmonitor.R
import com.pes.parentmonitor.activities.AlertsActivity
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class ParentFCMService : FirebaseMessagingService() {

    // Called when FCM issues a new registration token for this device.
    override fun onNewToken(token: String) {
        val prefs = PrefsManager(this)
        prefs.fcmToken = token
        if (prefs.isLoggedIn()) {
            registerTokenWithBackend(token, prefs)
        }
    }

    // Called when a data/notification message arrives while app is in background or foreground.
    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.notification?.title ?: "Parental Alert"
        val body  = message.notification?.body  ?: "Check your child's gaming activity"
        showNotification(title, body)
    }

    private fun showNotification(title: String, body: String) {
        val intent = Intent(this, AlertsActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pi = PendingIntent.getActivity(
            this, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(System.currentTimeMillis().toInt() and 0xFFFF, notif)
    }

    private fun registerTokenWithBackend(token: String, prefs: PrefsManager) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val body = mapOf<String, Any>("user_id" to prefs.parentId, "fcm_token" to token)
                api.updateFcmToken(body)
            } catch (_: Exception) {}
        }
    }
}
