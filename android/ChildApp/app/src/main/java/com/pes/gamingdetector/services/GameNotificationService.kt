package com.pes.gamingdetector.services

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.PrivacyText
import kotlinx.coroutines.*

class GameNotificationService : NotificationListenerService() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName
        if (!GameDetector.isGame(this, pkg)) return   // any game, not just the curated list

        val prefs = PrefsManager(this)
        if (!prefs.isLoggedIn()) return
        // Don't collect notification events until consent for the CURRENT policy is in
        // place — this listener is enabled at the OS level and would otherwise upload
        // game-notification titles before/without a valid consent (e.g. right after the
        // permission is granted but before the parent agrees, or under a changed policy).
        if (!prefs.consentDone || prefs.consentVersion != PrivacyText.CONSENT_VERSION) return

        // getCharSequence, not getString: many apps post the title as a SpannableString,
        // for which getString() returns null — silently dropping every title.
        val title = sbn.notification.extras
            .getCharSequence(android.app.Notification.EXTRA_TITLE)?.toString() ?: ""
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
