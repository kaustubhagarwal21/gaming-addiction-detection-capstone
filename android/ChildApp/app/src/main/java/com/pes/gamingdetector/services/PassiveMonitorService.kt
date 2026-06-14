package com.pes.gamingdetector.services

import android.app.KeyguardManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.activities.HomeActivity
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.StartSessionRequest
import com.pes.gamingdetector.util.ChatUploadQueue
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.ForegroundResolver
import com.pes.gamingdetector.util.ForegroundTracker
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.*

/**
 * Always-on background service that provides two passive data streams:
 *
 * 1. Auto-session detection — polls UsageStats (5s while active, 30s when locked +
 *    idle); when any game moves to the foreground a session is started on the server
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
    // Screen physically off (SCREEN_OFF → true, SCREEN_ON → false). Lock state itself
    // is read live from KeyguardManager (see locked()), not tracked here.
    @Volatile private var screenOff = false
    private val keyguard by lazy { getSystemService(KeyguardManager::class.java) }
    private val GRACE_MS    = 20_000L   // 20s grace when the user switches to a real app
    private val NEUTRAL_GRACE_MS = 120_000L  // 2 min when the game delegated to an ancillary flow
    private val POLL_MS     = 5_000L    // 5s when it matters: near-instant detection
    private val IDLE_POLL_MS = 30_000L  // device locked + no session → nothing to detect, save battery
    private val NUDGE_POLL_MS = 12_000L // how often to check for parent->child nudges (low-latency)
    private val HEARTBEAT_MS  = 180_000L // liveness ping every 3 min (tamper/uninstall watchdog + live "monitoring active" dot)

    private var screenReceiver: BroadcastReceiver? = null
    // onStartCommand can fire repeatedly on a LIVE service (START_STICKY redelivery, or
    // both BootReceiver and HomeActivity starting it). Without this guard each call would
    // register another screen receiver (leaking the previous one) and launch a second copy
    // of every loop — duplicate heartbeats/nudges and battery drain.
    @Volatile private var loopsStarted = false

    // Packages a game legitimately hands off to mid-play — Google sign-in, Play Store
    // purchases, the Play Games overlay, or a Custom-Tab browser (rewarded ads / login).
    // While the foreground sits in one of these we hold the session open with the longer
    // NEUTRAL grace so one continuous play session isn't split into two.
    private val ancillaryPackages: Set<String> by lazy {
        val set = mutableSetOf(
            "com.google.android.gms",
            "com.android.vending",
            "com.google.android.play.games",
        )
        try {
            val browse = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com"))
            packageManager.resolveActivity(browse, 0)?.activityInfo?.packageName?.let { set += it }
        } catch (_: Exception) {}
        set
    }
    private fun isAncillary(pkg: String?) =
        pkg != null && ancillaryPackages.any { pkg == it || pkg.startsWith("$it.") }

    companion object {
        const val NOTIF_ID = 1099
        const val ACTION_STOP = "com.pes.gamingdetector.STOP_PASSIVE"
    }

    // ── Lifecycle ─────────────────────────────────────────────────

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) { stopSelf(); return START_NOT_STICKY }

        prefs = PrefsManager(this)
        startForeground(NOTIF_ID, buildNotification())   // must happen on EVERY start (5s rule)
        // One-time setup, guarded so a repeat start doesn't leak a receiver or duplicate loops.
        if (!loopsStarted) {
            loopsStarted = true
            registerScreenReceiver()
            scope.launch { usageStatsLoop() }
            scope.launch { nudgeLoop() }
            scope.launch { heartbeatLoop() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        screenReceiver?.let { runCatching { unregisterReceiver(it) } }   // never throw on teardown
        screenReceiver = null
        loopsStarted = false
        super.onDestroy()
    }

    /** Child swiped the app away from recents — best-effort relaunch so monitoring survives.
     *  If even this fails, the server's heartbeat watchdog still alerts the parent. */
    override fun onTaskRemoved(rootIntent: Intent?) {
        try {
            val restart = Intent(applicationContext, PassiveMonitorService::class.java)
            val pi = PendingIntent.getService(
                this, 1, restart,
                PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE
            )
            val am = getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager
            am.set(android.app.AlarmManager.RTC, System.currentTimeMillis() + 1_000, pi)
        } catch (_: Exception) {}
        super.onTaskRemoved(rootIntent)
    }

    // ── Tamper watchdog: liveness ping ────────────────────────────
    // The status flags last successfully reported, as a compact key, so the poll loop can
    // fire an IMMEDIATE heartbeat the moment a flag flips (Android gives no callback when
    // a permission/setting is toggled) — making the parent's monitoring-health view
    // near-real-time instead of waiting out the ~5-min periodic heartbeat. "" = not yet
    // sent, so the first change always reports.
    @Volatile private var lastStatusKey: String = ""

    /** Current device-admin + capture-permission flags as a 4-char key (e.g. "1101"). */
    private fun statusKey(): String =
        "${if (isDeviceAdminActive()) 1 else 0}${if (hasUsageAccess()) 1 else 0}" +
        "${if (isAccessibilityOn()) 1 else 0}${if (isKeyboardActive()) 1 else 0}"

    /** Build + send one heartbeat (liveness + tz + status flags). Records the sent flags
     *  only on success, so a failed (offline) send is retried on the next change/tick. */
    private suspend fun sendHeartbeat() {
        if (!prefs.isLoggedIn() || prefs.userId == -1) return
        val key = statusKey()
        try {
            val tzMin = java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000
            ApiClient.getInstance(prefs.serverUrl).heartbeat(mapOf(
                "user_id" to prefs.userId,
                "tz_offset_min" to tzMin,
                "device_admin" to key[0].digitToInt(),
                "perm_usage" to key[1].digitToInt(),
                "perm_accessibility" to key[2].digitToInt(),
                "perm_keyboard" to key[3].digitToInt()))
            lastStatusKey = key
        } catch (_: Exception) { /* offline — server infers silence; retried next tick */ }
    }

    // A periodic heartbeat so the server can tell the parent if monitoring goes silent
    // (uninstalled / force-stopped / killed / offline). Runs as long as the service is
    // alive; when the service dies the pings stop and the server raises the alert.
    private suspend fun heartbeatLoop() {
        while (true) {
            sendHeartbeat()
            delay(HEARTBEAT_MS)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ── Parent -> child nudges ────────────────────────────────────
    // Polls the backend for messages the parent (or the system, on toxic chat) sent,
    // and pops each up as a notification on the child's phone. Runs always-on so a
    // nudge reaches the child even between gaming sessions.
    private suspend fun nudgeLoop() {
        while (currentCoroutineContext().isActive) {
            try {
                val uid = prefs.userId
                if (uid != -1) {
                    val resp = ApiClient.getInstance(prefs.serverUrl).getNudges(uid)
                    if (resp.isSuccessful && resp.body()?.success == true) {
                        resp.body()?.nudges?.forEach { showNudge(it.message, it.kind) }
                    }
                }
            } catch (_: Exception) { /* network blip — try again next tick */ }
            // Same cadence: retry any chat lines captured while offline (no-op when empty).
            try { ChatUploadQueue.flush(this@PassiveMonitorService) } catch (_: Exception) {}
            delay(NUDGE_POLL_MS)
        }
    }

    /** Is this app currently an active device administrator? (Instant uninstall-attempt
        alerting depends on it; reported in the heartbeat so the parent can see it.) */
    private fun isDeviceAdminActive(): Boolean = try {
        val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
        dpm.isAdminActive(android.content.ComponentName(this, AdminReceiver::class.java))
    } catch (_: Exception) { false }

    // ── Capture-permission health (reported in the heartbeat) ─────────────
    // Mirror the checks in HomeActivity so the parent dashboard can flag a running-but-
    // degraded monitor (e.g. the child revoked accessibility, silently stopping chat capture).
    private fun hasUsageAccess(): Boolean = try {
        val ops = getSystemService(Context.APP_OPS_SERVICE) as android.app.AppOpsManager
        val mode = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q)
            ops.unsafeCheckOpNoThrow(android.app.AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(), packageName)
        else @Suppress("DEPRECATION") ops.checkOpNoThrow(android.app.AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(), packageName)
        mode == android.app.AppOpsManager.MODE_ALLOWED
    } catch (_: Exception) { false }

    private fun isAccessibilityOn(): Boolean = try {
        (android.provider.Settings.Secure.getString(contentResolver,
            android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: "")
            .contains(packageName, ignoreCase = true)
    } catch (_: Exception) { false }

    private fun isKeyboardActive(): Boolean = try {
        (android.provider.Settings.Secure.getString(contentResolver,
            android.provider.Settings.Secure.DEFAULT_INPUT_METHOD) ?: "")
            .contains(packageName, ignoreCase = true)
    } catch (_: Exception) { false }

    private fun showNudge(message: String, kind: String?) {
        try {
            val title = when (kind) {
                "language" -> "A friendly reminder"
                "limit"    -> "Daily limit updated"
                "break"    -> "Time for a break"
                else       -> "Message from your parent"
            }
            val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(this)
                .notify(System.currentTimeMillis().toInt() and 0xFFFF, notif)
        } catch (_: SecurityException) { /* notifications not permitted — skip */ }
    }

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
                // Track screen on/off so an active session ends when the device is off
                // mid-game (UsageStats would otherwise keep reporting the game as the
                // most-recently-resumed app indefinitely). Whether the lock screen is up
                // is queried live from KeyguardManager in locked(), so we don't depend on
                // USER_PRESENT — which some devices/ROMs never broadcast when no secure
                // lock is set (common on a child's device).
                when (intent.action) {
                    Intent.ACTION_SCREEN_OFF -> screenOff = true
                    Intent.ACTION_SCREEN_ON  -> screenOff = false
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

    /** The device can't be actively used for gaming right now: the screen is off, or
        the lock screen (even a swipe keyguard) is showing. On a device with no lock set
        isKeyguardLocked() is false, so gaming is detected as soon as the screen is on —
        we don't rely on ACTION_USER_PRESENT, which isn't reliably sent without a lock. */
    private fun locked(): Boolean = screenOff || (keyguard?.isKeyguardLocked == true)

    private suspend fun usageStatsLoop() {
        while (currentCoroutineContext().isActive) {
            if (prefs.isLoggedIn()) {
                checkForegroundGame()
                // Near-real-time status: if a device-admin/permission flag flipped since the
                // last report, push a heartbeat NOW (this loop ticks every 5 s with the
                // screen on — i.e. exactly when the user is in Settings toggling things) so
                // the parent's monitoring-health view updates within seconds, not ~5 min.
                if (statusKey() != lastStatusKey) sendHeartbeat()
            }
            // Poll fast (5s) only when it matters — the screen is on, or a session is
            // running (so its grace-end stays prompt). While locked AND idle (phone in
            // a pocket, no game) there's nothing to detect, so back off to save battery.
            val fast = !locked() || prefs.hasActiveSession()
            delay(if (fast) POLL_MS else IDLE_POLL_MS)
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
            val stillPlaying = !locked() && foregroundPkg == trackedPackage
            // Switched straight to a DIFFERENT game (not a glance at home/our app)?
            val switchedToAnotherGame = !locked() &&
                foregroundPkg != null &&
                foregroundPkg != packageName &&
                foregroundPkg != trackedPackage &&
                GameDetector.isGame(this, foregroundPkg)
            if (stillPlaying) {
                gameLeftAt = 0L  // reset grace — game still running
            } else if (switchedToAnotherGame) {
                // Clean hand-off: end this game's session now so the next tick starts a
                // fresh session for the new game. Each game's time is attributed to it
                // instead of the first game silently absorbing the second's playtime.
                launchAutoEnd()
            } else {
                // Away from the game. If we're in an ancillary flow the game delegated to
                // (sign-in / purchase / rewarded-ad Custom Tab), use the longer NEUTRAL
                // grace so a single play session isn't split. A glance at home / our app /
                // any real other app uses the short grace; sitting there past it ends the
                // session. The grace is chosen from the CURRENT foreground each tick, so
                // moving from an ad to the home screen correctly falls back to the short one.
                if (gameLeftAt == 0L) {
                    gameLeftAt = System.currentTimeMillis()
                }
                val grace = if (isAncillary(foregroundPkg)) NEUTRAL_GRACE_MS else GRACE_MS
                val awayMs = System.currentTimeMillis() - gameLeftAt
                if (awayMs > grace) {
                    // Attribute time only up to when play actually stopped — exclude the
                    // grace/ancillary tail the user was no longer in the game.
                    launchAutoEnd(endedSecondsAgo = awayMs / 1000)
                }
            }
        } else {
            // ── Detection mode: no session yet ────────────────────────────────────
            // Start a session only if the device is unlocked AND the current foreground
            // app is a game. The unlock check stops a session spawning while the game is
            // still the last-resumed app behind the lock/password screen.
            if (!locked() &&
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
    private fun launchAutoEnd(endedSecondsAgo: Long = 0L) {
        if (endingSession) return
        endingSession = true
        trackedPackage = ""
        gameLeftAt = 0L
        scope.launch {
            try { performAutoEnd(endedSecondsAgo) } finally { endingSession = false }
        }
    }

    private suspend fun performAutoEnd(endedSecondsAgo: Long) {
        val sessionId = prefs.activeSessionId
        val gameName  = prefs.activeSessionGame
        if (sessionId == -1) return
        try {
            stopService(Intent(this, GameMonitorService::class.java))
            val resp = ApiClient.getInstance(prefs.serverUrl).endSession(sessionId, endedSecondsAgo)
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
