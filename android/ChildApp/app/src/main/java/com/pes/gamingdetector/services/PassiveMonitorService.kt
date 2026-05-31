package com.pes.gamingdetector.services

import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.activities.HomeActivity
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.StartSessionRequest
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.ForegroundResolver
import com.pes.gamingdetector.util.ForegroundTracker
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.*

/**
 * Always-on background service that provides two passive data streams:
 *
 * 1. Auto-session detection — polls UsageStats every 30s; when a known game
 *    moves to the foreground a session is started automatically on the server
 *    and GameMonitorService is launched. When the game leaves foreground for
 *    more than GRACE_PERIOD_MS the session is ended automatically.
 *    This means all gaming is captured regardless of whether the child opens
 *    the app or presses "Start Session".
 *
 * 2. Screen event logging — a dynamically registered BroadcastReceiver fires
 *    on every screen-on / screen-off / unlock event. These zero-permission
 *    events let the backend measure late-night device activity (a direct
 *    sleep disruption signal) even between sessions.
 */
class PassiveMonitorService : Service() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PrefsManager

    // Auto-session state
    private var trackedPackage: String = ""
    private var gameLeftAt: Long = 0L
    @Volatile private var startingSession = false  // guards the async startSession round-trip
    @Volatile private var endingSession = false    // guards the async endSession round-trip
    // True while the device is off OR on the lock screen. Cleared only when the user
    // actually unlocks (USER_PRESENT) — not merely when the screen turns on — so a
    // session can't start while the password screen is up and the game is still the
    // last-resumed app behind it.
    @Volatile private var screenLocked = false
    private val GRACE_MS = 20_000L   // 20s grace — short enough to feel responsive
    private val POLL_MS  = 5_000L    // poll every 5s for near-instant detection

    private var screenReceiver: BroadcastReceiver? = null

    companion object {
        const val NOTIF_ID = 1099
        const val ACTION_STOP = "com.pes.gamingdetector.STOP_PASSIVE"
    }

    // ── Lifecycle ─────────────────────────────────────────────────

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) { stopSelf(); return START_NOT_STICKY }

        prefs = PrefsManager(this)
        startForeground(NOTIF_ID, buildNotification())
        registerScreenReceiver()
        scope.launch { usageStatsLoop() }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        screenReceiver?.let { unregisterReceiver(it) }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ── Notification ──────────────────────────────────────────────

    private fun buildNotification() =
        NotificationCompat.Builder(this, Constants.CHANNEL_MONITORING)
            .setContentTitle("Gaming Monitor Active")
            .setContentText("Watching for gaming activity")
            .setSmallIcon(R.drawable.ic_launcher)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setContentIntent(
                PendingIntent.getActivity(
                    this, 0,
                    Intent(this, HomeActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
            )
            .build()

    // ── Screen event tracking ─────────────────────────────────────

    private fun registerScreenReceiver() {
        screenReceiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                val type = when (intent.action) {
                    Intent.ACTION_SCREEN_ON    -> "screen_on"
                    Intent.ACTION_SCREEN_OFF   -> "screen_off"
                    Intent.ACTION_USER_PRESENT -> "unlocked"
                    else                       -> return
                }
                // Track lock state so an active session ends when the device is locked
                // mid-game (UsageStats would otherwise keep reporting the game as the
                // most-recently-resumed app indefinitely). SCREEN_ON keeps it locked —
                // the keyguard/password screen is still up — only USER_PRESENT (real
                // unlock) clears it.
                when (intent.action) {
                    Intent.ACTION_SCREEN_OFF   -> screenLocked = true
                    Intent.ACTION_USER_PRESENT -> screenLocked = false
                }
                if (prefs.isLoggedIn()) {
                    scope.launch { postScreenEvent(type) }
                }
            }
        }
        registerReceiver(
            screenReceiver,
            IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_USER_PRESENT)
            }
        )
    }

    private suspend fun postScreenEvent(eventType: String) {
        try {
            ApiClient.getInstance(prefs.serverUrl).postScreenEvent(
                mapOf(
                    "user_id"    to prefs.userId.toString(),
                    "event_type" to eventType,
                    "timestamp"  to System.currentTimeMillis().toString()
                )
            )
        } catch (_: Exception) {}
    }

    // ── Auto-session detection ────────────────────────────────────

    private suspend fun usageStatsLoop() {
        while (currentCoroutineContext().isActive) {
            if (prefs.isLoggedIn()) {
                checkForegroundGame()
            }
            delay(POLL_MS)
        }
    }

    private fun checkForegroundGame() {
        // A session end is in flight (async endSession + clearSession). Skip this tick
        // so we don't re-adopt the still-active-in-prefs session and double-end it.
        if (endingSession) return

        val sessionActive = prefs.hasActiveSession()
        val foregroundPkg = ForegroundResolver.current(this)

        // Re-adopt an orphaned session: if the service restarted mid-session (e.g.
        // after a reinstall) the in-memory trackedPackage is lost while prefs still
        // holds the active session. Recover the package from the saved game name so
        // maintenance mode resumes; if it can't be mapped, end the stale session.
        if (sessionActive && trackedPackage.isEmpty()) {
            // Prefer the stored package (works for any game); fall back to mapping the
            // saved name for sessions started before the package was persisted.
            val pkg = prefs.activeSessionPackage.ifEmpty {
                Constants.PACKAGE_TO_GAME.entries
                    .firstOrNull { it.value == prefs.activeSessionGame }?.key ?: ""
            }
            if (pkg.isNotEmpty()) {
                trackedPackage = pkg
            } else {
                launchAutoEnd()
                return
            }
        }

        if (sessionActive && trackedPackage.isNotEmpty()) {
            // ── Maintenance mode: session is running ──────────────────────────────
            // Still playing only if the screen is unlocked AND the tracked game is the
            // foreground app. Anything else — locked, ChildApp, another app — starts the
            // grace timer. The 20s grace still absorbs a quick glance at ChildApp and a
            // return to the game; sitting in ChildApp (or any non-game app) ends it.
            val stillPlaying = !screenLocked && foregroundPkg == trackedPackage
            if (stillPlaying) {
                gameLeftAt = 0L  // reset grace — game still running
            } else {
                if (gameLeftAt == 0L) {
                    gameLeftAt = System.currentTimeMillis()
                } else if (System.currentTimeMillis() - gameLeftAt > GRACE_MS) {
                    launchAutoEnd()
                }
            }
        } else {
            // ── Detection mode: no session yet ────────────────────────────────────
            // Start a session only if the device is unlocked AND the current foreground
            // app is a known game. The unlock check stops a session spawning while the
            // game is still the last-resumed app behind the lock/password screen.
            if (!screenLocked &&
                !startingSession &&
                foregroundPkg != null &&
                foregroundPkg != packageName &&
                GameDetector.isGame(this, foregroundPkg)
            ) {
                // startingSession stays true across the whole async startSession call
                // so subsequent 5s ticks can't fire a second start before the first
                // session is registered.
                startingSession = true
                val pkg = foregroundPkg
                val gameName = GameDetector.displayName(this, pkg)
                scope.launch {
                    try { performAutoStart(gameName, pkg) }
                    finally { startingSession = false }
                }
            }
        }
    }

    private suspend fun performAutoStart(gameName: String, pkg: String) {
        if (prefs.hasActiveSession()) return  // already tracking
        try {
            val api  = ApiClient.getInstance(prefs.serverUrl)
            val resp = api.startSession(StartSessionRequest(prefs.userId, gameName))
            if (resp.isSuccessful && resp.body()?.success == true) {
                val sessionId = resp.body()!!.sessionId
                prefs.activeSessionId      = sessionId
                prefs.activeSessionGame    = gameName
                prefs.activeSessionPackage = pkg   // for orphan recovery of any game
                prefs.activeSessionStart   = System.currentTimeMillis()
                // Tie trackedPackage to an actually-created session so a failed start
                // doesn't leave a phantom tracked package behind.
                trackedPackage = pkg
                gameLeftAt = 0L

                // Launch GameMonitorService (behavioral data + voice analysis)
                ContextCompat.startForegroundService(
                    this,
                    Intent(this, GameMonitorService::class.java).apply {
                        putExtra("session_id", sessionId)
                        putExtra("game_name", gameName)
                        putExtra("user_id", prefs.userId)
                        putExtra("server_url", prefs.serverUrl)
                    }
                )
            }
        } catch (_: Exception) {}
    }

    // Clears tracked state synchronously and runs the async end behind a guard so
    // repeated 5s ticks can't fire a second endSession before this one completes.
    private fun launchAutoEnd() {
        if (endingSession) return
        endingSession = true
        trackedPackage = ""
        gameLeftAt = 0L
        scope.launch {
            try { performAutoEnd() } finally { endingSession = false }
        }
    }

    private suspend fun performAutoEnd() {
        val sessionId = prefs.activeSessionId
        val gameName  = prefs.activeSessionGame
        if (sessionId == -1) return
        try {
            stopService(Intent(this, GameMonitorService::class.java))
            val resp = ApiClient.getInstance(prefs.serverUrl).endSession(sessionId)
            prefs.clearSession()
            if (resp.isSuccessful) {
                val pred = resp.body()?.prediction
                val category = pred?.riskLabel ?: "unknown"
                val score    = pred?.riskScore
                val scoreStr = if (score != null) " (${(score * 100).toInt()}%)" else ""
                val emoji = when (category.lowercase()) {
                    "casual"   -> "✅"
                    "at_risk"  -> "⚠️"
                    "addicted" -> "🔴"
                    else       -> "🎮"
                }
                showSessionEndNotification(gameName, "$emoji ${category.replace('_', ' ').replaceFirstChar { it.uppercase() }}$scoreStr")
            }
        } catch (_: Exception) {
            prefs.clearSession()
        }
    }

    private fun showSessionEndNotification(gameName: String, riskLine: String) {
        val intent = PendingIntent.getActivity(
            this, 0,
            Intent(this, HomeActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("$gameName session ended")
            .setContentText("Risk level: $riskLine")
            .setAutoCancel(true)
            .setContentIntent(intent)
            .build()
        val nm = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        nm.notify(Constants.NOTIF_SESSION_END, notif)
    }
}
