package com.pes.gamingdetector.services

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.*

class GameNotificationService : NotificationListenerService() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName
        if (!GameDetector.isGame(this, pkg)) return   // any game, not just the curated list

        val prefs = PrefsManager(this)
        if (!prefs.isLoggedIn()) return

        val title = sbn.notification.extras
            .getString(android.app.Notification.EXTRA_TITLE) ?: ""
        val gameName = GameDetector.displayName(this, pkg)

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
