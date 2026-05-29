package com.pes.gamingdetector.services

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.*

class GameNotificationService : NotificationListenerService() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName
        if (pkg !in Constants.KNOWN_GAMING_PACKAGES) return

        val prefs = PrefsManager(this)
        if (!prefs.isLoggedIn()) return

        val title = sbn.notification.extras
            .getString(android.app.Notification.EXTRA_TITLE) ?: ""
        val gameName = Constants.PACKAGE_TO_GAME[pkg] ?: pkg.substringAfterLast('.')

        scope.launch {
            try {
                ApiClient.getInstance(prefs.serverUrl).postNotificationEvent(
                    mapOf(
                        "user_id"            to prefs.userId.toString(),
                        "package_name"       to pkg,
                        "game_name"          to gameName,
                        "notification_title" to title.take(100)
                    )
                )
            } catch (_: Exception) {}
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
