package com.pes.gamingdetector.services

import android.app.KeyguardManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.activities.HomeActivity
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.StartSessionRequest
import com.pes.gamingdetector.util.ChatUploadQueue
import com.pes.gamingdetector.util.CaptureHealthLogic
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.ForegroundResolver
import com.pes.gamingdetector.util.ForegroundTracker
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.OfflineSessionBuffer
import com.pes.gamingdetector.util.OfflineSessionLogic
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.RiskPresentation
import com.pes.gamingdetector.util.SessionEndLogic
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
    // Keep both clocks: epoch is persisted/sent to the server as the real stop instant;
    // elapsedRealtime is used only for the in-process grace duration so a wall-clock
    // correction cannot end a session early or hold it open indefinitely.
    private var gameLeftAtEpochMs: Long = 0L
    private var gameLeftAtElapsedMs: Long = 0L
    @Volatile private var startingSession = false  // guards the async startSession round-trip
    @Volatile private var endingSession = false    // guards the async endSession round-trip
    @Volatile private var pendingStartPackage = ""
    @Volatile private var pendingStartLastSeenMs = 0L
    private var lastEndAttemptElapsedMs = 0L
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
    private val OFFLINE_CHECKPOINT_MS = 30_000L

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
        // START_STICKY may recreate the service without passing through Home/Boot. Fail
        // closed here so an expired login or stale/declined consent can never resume
        // screen/session collection merely because Android restarted the process.
        if (!prefs.canMonitor()) {
            stopSelf()
            return START_NOT_STICKY
        }
        // One-time setup, guarded so a repeat start doesn't leak a receiver or duplicate loops.
        if (!loopsStarted) {
            loopsStarted = true
            // A sticky restart can happen while the display is already off, after the
            // SCREEN_OFF broadcast was missed. Initialise from live state before the
            // UsageStats loop sees the last-resumed game and starts a phantom session.
            screenOff = !(getSystemService(PowerManager::class.java)?.isInteractive ?: true)
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
        if (!::prefs.isInitialized || !prefs.canMonitor()) {
            super.onTaskRemoved(rootIntent)
            return
        }
        try {
            val restart = Intent(applicationContext, PassiveMonitorService::class.java)
            // getForegroundService, not getService: on minSdk 26+ starting a plain
            // background service is restricted and the alarm restart would silently
            // no-op. The service calls startForeground() on every start, so a
            // foreground-service PendingIntent is the correct (and permitted) restart.
            val pi = PendingIntent.getForegroundService(
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
    // Last ATTEMPTED key + when (elapsedRealtime). While offline / during a backend
    // cold start, lastStatusKey never becomes current, and the fast 5-second poll loop
    // used to re-fire a doomed network POST on every tick — indefinitely — draining the
    // child's battery. A retry of the SAME failing key now waits HEARTBEAT_RETRY_MS;
    // a genuine flag CHANGE (different key) still reports instantly, and the 3-minute
    // heartbeatLoop keeps its unconditional cadence either way.
    @Volatile private var lastAttemptKey: String = ""
    @Volatile private var lastAttemptElapsedMs: Long = 0L
    private val HEARTBEAT_RETRY_MS = 60_000L

    /** Current device-admin + capture-permission flags. Voice uses u while unknown. */
    private fun statusKey(): String =
        "${if (isDeviceAdminActive()) 1 else 0}${if (hasUsageAccess()) 1 else 0}" +
        "${if (isAccessibilityOn()) 1 else 0}${if (isKeyboardActive()) 1 else 0}" +
        when (prefs.voiceCaptureActive) {
            true -> "1"
            false -> "0"
            null -> "u"
        }

    /** Build + send one heartbeat (liveness + tz + status flags). Records the sent flags
     *  only on success, so a failed (offline) send is retried on the next change/tick. */
    private suspend fun sendHeartbeat() {
        if (!prefs.isLoggedIn() || prefs.userId == -1) return
        val key = statusKey()
        lastAttemptKey = key
        lastAttemptElapsedMs = android.os.SystemClock.elapsedRealtime()
        try {
            val tzMin = java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000
            val body = mutableMapOf<String, Any>(
                "user_id" to prefs.userId,
                "tz_offset_min" to tzMin,
                "device_admin" to key[0].digitToInt(),
                "perm_usage" to key[1].digitToInt(),
                "perm_accessibility" to key[2].digitToInt(),
                "perm_keyboard" to key[3].digitToInt())
            prefs.voiceCaptureActive?.let { body["voice_capture"] = if (it) 1 else 0 }
            val resp = ApiClient.getInstance(prefs.serverUrl).heartbeat(body)
            // Retrofit returns normally on 4xx/5xx. Only remember a status as delivered
            // after a real success, otherwise the next fast tick must retry it.
            if (resp.isSuccessful && resp.body()?.success == true) lastStatusKey = key
            // 403 on the heartbeat means exactly one thing: the server will not accept
            // monitoring data under the current consent state (withdrawn, or a policy
            // version newer than this build). guard() cannot 403 here — the caller is
            // always its own user — so no other case is conflated. Stop capturing NOW
            // rather than continuing to record locally until the child next opens the
            // app; HomeActivity re-runs the consent flow on the next launch.
            else if (resp.code() == 403) {
                android.util.Log.w("PassiveMonitor",
                    "server refused data (consent) — stopping capture")
                prefs.revokeConsentLocally()
                stopCaptureAfterConsentLoss()
            }
        } catch (_: Exception) { /* offline — server infers silence; retried next tick */ }
    }

    /** Tear down every capture path the moment consent stops being valid. */
    private fun stopCaptureAfterConsentLoss() {
        runCatching { stopService(Intent(this, VoiceRecorderService::class.java)) }
        runCatching { stopService(Intent(this, GameMonitorService::class.java)) }
        stopSelf()
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
                        val shownIds = resp.body()?.nudges.orEmpty()
                            .filter { showNudge(it.id, it.message, it.kind) }
                            .map { it.id }
                        // GET is now non-destructive. Acknowledge only notifications the
                        // OS accepted; denied notification permission/process death leaves
                        // them pending for a later retry instead of losing them forever.
                        if (shownIds.isNotEmpty()) {
                            ApiClient.getInstance(prefs.serverUrl).ackNudges(
                                mapOf("user_id" to prefs.userId, "nudge_ids" to shownIds)
                            )
                            // A failed ack is harmless: stable notification ids replace
                            // the existing cards on the next poll rather than duplicating.
                        }
                    }
                }
            } catch (_: Exception) { /* network blip — try again next tick */ }
            // Same cadence: retry anything captured while offline (no-op when empty) —
            // chat lines and back-fillable offline sessions.
            try { ChatUploadQueue.flush(this@PassiveMonitorService) } catch (_: Exception) {}
            try { OfflineSessionBuffer.flush(this@PassiveMonitorService) } catch (_: Exception) {}
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

    // Self-heal for silently-lost capture permissions. A monitored child rarely opens
    // the app (they just play games), so HomeActivity's on-resume re-prompt never fires —
    // in the pilot the Wellbeing Keyboard sat OFF for days after an OS default-IME reset.
    // This edge-triggered check runs in the always-on monitor loop: when accessibility or
    // the keyboard flips from ON to OFF it posts ONE notification that opens HomeActivity,
    // whose existing permission chain then walks the child through re-enabling it. Only
    // fires on the 1->0 transition (not every tick while off), and only after a baseline
    // exists (never nags a child who hasn't set it up yet).
    @Volatile private var lastCaptureBits: String? = null

    private fun checkCaptureRegression() {
        val bits = "${if (isAccessibilityOn()) 1 else 0}${if (isKeyboardActive()) 1 else 0}"
        // Recover the previous observation from encrypted preferences after a reboot or
        // process restart. A RAM-only baseline misses exactly the OS-reset case this
        // self-heal exists for: the new process first observes OFF and never sees 1 -> 0.
        val prev = lastCaptureBits
            ?: prefs.lastCaptureBits.takeIf { it.length == 2 }
        lastCaptureBits = bits
        if (prefs.lastCaptureBits != bits) prefs.lastCaptureBits = bits
        when (CaptureHealthLogic.loss(prev, bits)) {
            CaptureHealthLogic.Loss.KEYBOARD -> notifyReenable(
                NOTIF_ID + 7,
                "Wellbeing Keyboard turned off",
                "In-game chat capture is paused. Tap to switch it back on.")
            CaptureHealthLogic.Loss.ACCESSIBILITY -> notifyReenable(
                NOTIF_ID + 8,
                "Chat monitoring turned off",
                "Accessibility was disabled. Tap to re-enable gaming-wellbeing monitoring.")
            null -> Unit
        }
    }

    /** One-tap self-heal: opens HomeActivity, which re-runs the permission chain and shows
     *  the exact re-enable dialog. Same notification-permission tolerance as showNudge.
     *  Distinct id per loss kind: with a shared id, losing accessibility after the
     *  keyboard replaced the keyboard prompt before the child could act on it. */
    private fun notifyReenable(notificationId: Int, title: String, text: String) {
        try {
            val pi = PendingIntent.getActivity(
                this, notificationId, Intent(this, HomeActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val notif = NotificationCompat.Builder(this, Constants.CHANNEL_ALERTS)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(this).notify(notificationId, notif)
        } catch (_: SecurityException) { /* notifications not permitted — skip */ }
    }

    private fun showNudge(id: Int, message: String, kind: String?): Boolean {
        return try {
            if (!NotificationManagerCompat.from(this).areNotificationsEnabled()) return false
            // notify() succeeds even when this one channel is disabled. Do not ACK and
            // destroy the server nudge unless the child can actually see the card.
            val channel = getSystemService(NotificationManager::class.java)
                ?.getNotificationChannel(Constants.CHANNEL_ALERTS)
            if (channel == null || channel.importance == NotificationManager.IMPORTANCE_NONE) {
                return false
            }
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
            // Stable, namespaced id: several nudges returned in one poll used the same
            // millisecond-derived id and overwrote one another before the child saw them.
            val notificationId = 0x4E000000 or (id and 0x00FFFFFF)
            NotificationManagerCompat.from(this).notify(notificationId, notif)
            true
        } catch (_: SecurityException) {
            false
        } catch (_: Exception) {
            false
        }
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
                // Screen timing is monitoring data like any other — gate it on consent,
                // not merely on being signed in.
                if (prefs.canMonitor()) {
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
            // canMonitor(), not isLoggedIn(): consent can lapse while the service runs
            // (policy bump or withdrawal, detected by the heartbeat above). Session and
            // screen collection must stop with it, not merely fail server-side.
            if (!prefs.canMonitor()) {
                stopCaptureAfterConsentLoss()
                return
            }
            if (prefs.isLoggedIn()) {
                checkForegroundGame()
                // Near-real-time status: if a device-admin/permission flag flipped since the
                // last report, push a heartbeat NOW (this loop ticks every 5 s with the
                // screen on — i.e. exactly when the user is in Settings toggling things) so
                // the parent's monitoring-health view updates within seconds, not ~5 min.
                // Backoff: only when the key actually CHANGED since the last attempt, or
                // the same-key retry window elapsed — never a failed POST per 5 s tick.
                val key = statusKey()
                if (key != lastStatusKey &&
                    (key != lastAttemptKey ||
                        android.os.SystemClock.elapsedRealtime() - lastAttemptElapsedMs >=
                            HEARTBEAT_RETRY_MS)) {
                    sendHeartbeat()
                }
                checkCaptureRegression()
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

        // A previous end attempt may have failed or the process may have died while it was
        // in flight. Retry the SAME durable stop instant instead of re-starting the grace
        // clock and counting the offline/server-outage gap as play time.
        if (sessionActive && prefs.pendingEndSessionId == prefs.activeSessionId &&
            prefs.pendingEndStoppedAt > 0L) {
            val nowElapsed = android.os.SystemClock.elapsedRealtime()
            if (!endingSession &&
                (lastEndAttemptElapsedMs == 0L ||
                    nowElapsed - lastEndAttemptElapsedMs >= GRACE_MS)) {
                launchAutoEnd(prefs.pendingEndStoppedAt)
            }
            return
        } else if (prefs.pendingEndSessionId != -1) {
            // Marker from a session that is no longer active; never apply it to a new id.
            prefs.clearPendingEnd()
        }

        // While the start request is in flight, remember the last tick on which its game
        // was definitely foreground. If the request times out after the child already
        // left, this bounds the locally completed interval instead of counting the whole
        // 30-90 second network timeout as play.
        if (!sessionActive && startingSession && !locked() &&
            foregroundPkg == pendingStartPackage) {
            pendingStartLastSeenMs = System.currentTimeMillis()
        }

        // A game can begin AND end while the phone has no network. Finalize that local
        // bout as soon as it leaves foreground; waiting for a later successful start of
        // the same title used to back-fill the intervening hours/days as fake play time.
        if (!sessionActive && !startingSession) {
            reconcileOfflineMarker(foregroundPkg)
        }

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
                gameLeftAtEpochMs = 0L  // reset grace — game still running
                gameLeftAtElapsedMs = 0L
            } else if (switchedToAnotherGame) {
                // Clean hand-off: end this game's session now so the next tick starts a
                // fresh session for the new game. Each game's time is attributed to it
                // instead of the first game silently absorbing the second's playtime.
                launchAutoEnd(System.currentTimeMillis())
            } else {
                // Away from the game. If we're in an ancillary flow the game delegated to
                // (sign-in / purchase / rewarded-ad Custom Tab), use the longer NEUTRAL
                // grace so a single play session isn't split. A glance at home / our app /
                // any real other app uses the short grace; sitting there past it ends the
                // session. The grace is chosen from the CURRENT foreground each tick, so
                // moving from an ad to the home screen correctly falls back to the short one.
                if (gameLeftAtElapsedMs == 0L) {
                    gameLeftAtEpochMs = System.currentTimeMillis()
                    gameLeftAtElapsedMs = android.os.SystemClock.elapsedRealtime()
                }
                val grace = if (isAncillary(foregroundPkg)) NEUTRAL_GRACE_MS else GRACE_MS
                val awayMs = android.os.SystemClock.elapsedRealtime() - gameLeftAtElapsedMs
                if (awayMs > grace) {
                    // Attribute time only up to when play actually stopped — exclude the
                    // grace/ancillary tail the user was no longer in the game.
                    launchAutoEnd(gameLeftAtEpochMs)
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
                val detectedAt = System.currentTimeMillis()
                pendingStartPackage = pkg
                pendingStartLastSeenMs = detectedAt
                scope.launch {
                    try { performAutoStart(gameName, pkg, detectedAt) }
                    finally {
                        pendingStartPackage = ""
                        pendingStartLastSeenMs = 0L
                        startingSession = false
                    }
                }
            }
        }
    }

    /** Complete a persisted offline marker when its game is no longer foreground. */
    private fun reconcileOfflineMarker(foregroundPkg: String?) {
        val start = prefs.offlineSessionStartMs
        if (start <= 0L) return
        val storedPkg = prefs.offlineSessionPackage
        val stillPlaying = !locked() && foregroundPkg != null &&
            (storedPkg == foregroundPkg ||
                (storedPkg.isBlank() && runCatching {
                    GameDetector.displayName(this, foregroundPkg) == prefs.offlineSessionGame
                }.getOrDefault(false)))
        val now = System.currentTimeMillis()
        if (stillPlaying) {
            if (now - prefs.offlineSessionLastSeenMs >= OFFLINE_CHECKPOINT_MS) {
                prefs.touchOfflineSession(now)
            }
            return
        }
        finishOfflineMarker(now)
    }

    private fun finishOfflineMarker(nowMs: Long): Boolean {
        val start = prefs.offlineSessionStartMs
        if (start <= 0L) return true
        val end = OfflineSessionLogic.boundedEnd(
            start,
            prefs.offlineSessionLastSeenMs,
            nowMs,
            POLL_MS
        )
        val saved = OfflineSessionBuffer.record(
            this,
            prefs.offlineSessionGame,
            start,
            end,
            prefs.offlineSessionKey
        )
        // Never clear the only durable copy if the queue commit failed.
        if (saved) prefs.clearOfflineSession()
        return saved
    }

    /** Persist or finish an offline bout after a retryable start failure. */
    private fun handleTransientStartFailure(gameName: String, pkg: String, detectedAt: Long) {
        val now = System.currentTimeMillis()
        val currentPkg = ForegroundResolver.current(this)
        val stillPlaying = !locked() && currentPkg == pkg

        // Normally reconcileOfflineMarker handled a previous game's marker before this
        // request launched. Keep the fallback safe across a process restore/race.
        if (prefs.offlineSessionStartMs > 0L &&
            prefs.offlineSessionPackage.isNotBlank() &&
            prefs.offlineSessionPackage != pkg) {
            if (!finishOfflineMarker(now)) return
        }

        val existing = prefs.offlineSessionStartMs > 0L &&
            (prefs.offlineSessionPackage == pkg ||
                (prefs.offlineSessionPackage.isBlank() && prefs.offlineSessionGame == gameName))
        val start = if (existing) prefs.offlineSessionStartMs else detectedAt
        val key = if (existing) prefs.offlineSessionKey else java.util.UUID.randomUUID().toString()
        val lastSeen = maxOf(start, prefs.offlineSessionLastSeenMs, pendingStartLastSeenMs)

        if (stillPlaying) {
            if (!existing) {
                prefs.markOfflineSession(gameName, pkg, start, key, lastSeen)
            } else if (lastSeen > prefs.offlineSessionLastSeenMs) {
                prefs.touchOfflineSession(lastSeen)
            }
        } else {
            val end = OfflineSessionLogic.boundedEnd(start, lastSeen, now, POLL_MS)
            val saved = OfflineSessionBuffer.record(this, gameName, start, end, key)
            if (saved && existing) {
                prefs.clearOfflineSession()
            } else if (!saved && !existing) {
                // Keep a retryable marker when the first queue commit itself failed.
                prefs.markOfflineSession(gameName, pkg, start, key, lastSeen)
            }
        }
    }

    private suspend fun performAutoStart(gameName: String, pkg: String, detectedAt: Long) {
        if (prefs.hasActiveSession()) return  // already tracking
        val api = ApiClient.getInstance(prefs.serverUrl)
        val resp = try {
            api.startSession(StartSessionRequest(prefs.userId, gameName))
        } catch (_: java.io.IOException) {
            handleTransientStartFailure(gameName, pkg, detectedAt)
            return
        } catch (_: Exception) {
            // A serialization/programming error is not evidence that the phone was
            // offline. Marking it as such can duplicate a session the server created
            // successfully but whose unexpected response failed to decode.
            return
        }
        if (!resp.isSuccessful || resp.body()?.success != true) {
            if (OfflineSessionLogic.isTransientStartFailure(resp.code())) {
                handleTransientStartFailure(gameName, pkg, detectedAt)
            }
            return
        }

        // From here on the server session definitely exists. Keep failures in local
        // service startup/prefs work out of the network-failure path; the old broad catch
        // created a second offline marker for an already-created server session.
        try {
                val body = resp.body()!!
                val sessionId = body.sessionId
                if (sessionId <= 0) return
                val saved = prefs.saveActiveSession(
                    sessionId,
                    gameName,
                    pkg,
                    System.currentTimeMillis()
                )
                if (!saved) {
                    // The server session exists, but it cannot be recovered after process
                    // death without durable local state. Close it immediately rather than
                    // launching an un-endable/orphaned monitor.
                    val closed = try {
                        val end = api.endSession(sessionId)
                        end.isSuccessful && end.body()?.success == true
                    } catch (_: Exception) {
                        false
                    }
                    if (closed) {
                        prefs.clearSession()
                    } else {
                        // commit() updates the in-process preference map even when its disk
                        // write reports false. Keep monitoring/retrying in this process and
                        // make one more durable write attempt for the original instant.
                        prefs.markPendingEnd(sessionId, System.currentTimeMillis())
                        trackedPackage = pkg
                        gameLeftAtEpochMs = 0L
                        gameLeftAtElapsedMs = 0L
                        ensureGameMonitorService()
                    }
                    return
                }
                // Tie trackedPackage to an actually-created session so a failed start
                // doesn't leave a phantom tracked package behind.
                trackedPackage = pkg
                gameLeftAtEpochMs = 0L
                gameLeftAtElapsedMs = 0L

                // Offline-head backfill: if this SAME game had begun while offline (a
                // start we couldn't register then), the span from that offline start until
                // now is an untracked session that just came online — record it so it
                // becomes a real, scored, parent-visible session instead of vanishing.
                // A different game means the offline attempt was abandoned; either way we
                // clear the marker so it can't leak into a later unrelated session.
                val offStart = prefs.offlineSessionStartMs
                val sameOfflineBout = offStart > 0L &&
                    (prefs.offlineSessionPackage == pkg ||
                        (prefs.offlineSessionPackage.isBlank() && prefs.offlineSessionGame == gameName))
                if (sameOfflineBout) {
                    if (body.reused) {
                        // The first start reached the server and only its response was
                        // lost. Its open session already covers this interval.
                        prefs.clearOfflineSession()
                    } else if (OfflineSessionBuffer.record(this, gameName, offStart,
                            detectedAt, prefs.offlineSessionKey)) {
                        prefs.clearOfflineSession()
                    }
                } else if (offStart > 0L) {
                    finishOfflineMarker(detectedAt)
                }

                // Launch GameMonitorService (behavioral data + voice analysis)
                ensureGameMonitorService()
        } catch (_: Exception) { /* server session exists; maintenance/end recovery handles it */ }
    }

    // Clears tracked state synchronously and runs the async end behind a guard so
    // repeated 5s ticks can't fire a second endSession before this one completes.
    private fun launchAutoEnd(stoppedAtMs: Long = System.currentTimeMillis()) {
        if (endingSession) return
        val sessionId = prefs.activeSessionId
        if (sessionId <= 0) return
        val existingStop = if (prefs.pendingEndSessionId == sessionId)
            prefs.pendingEndStoppedAt else 0L
        val durableStop = existingStop.takeIf { it > 0L }
            ?: stoppedAtMs.coerceAtMost(System.currentTimeMillis())
        if (existingStop <= 0L && !prefs.markPendingEnd(sessionId, durableStop)) {
            // Keep the tracked/grace state intact and retry persistence on the next tick.
            return
        }
        endingSession = true
        lastEndAttemptElapsedMs = android.os.SystemClock.elapsedRealtime()
        trackedPackage = ""
        gameLeftAtEpochMs = 0L
        gameLeftAtElapsedMs = 0L
        val gameName = prefs.activeSessionGame
        scope.launch {
            try { performAutoEnd(sessionId, gameName, durableStop) }
            finally { endingSession = false }
        }
    }

    private suspend fun performAutoEnd(
        sessionId: Int,
        gameName: String,
        stoppedAtMs: Long
    ) {
        if (sessionId <= 0 || prefs.activeSessionId != sessionId) return
        try {
            val endedSecondsAgo = SessionEndLogic.endedSecondsAgo(
                stoppedAtMs,
                System.currentTimeMillis()
            )
            val resp = ApiClient.getInstance(prefs.serverUrl)
                .endSession(sessionId, endedSecondsAgo)
            when {
                resp.isSuccessful && resp.body()?.success == true -> {
                    // Only clear the local session once the server has actually recorded the
                    // end. Clearing on failure (the old behaviour) orphaned the server
                    // session — it stayed "playing" until the 6h stale fallback and then
                    // recorded a zero-duration session.
                    prefs.clearSession()
                    stopService(Intent(this, GameMonitorService::class.java))
                    val pred = resp.body()?.prediction
                    val category = pred?.riskLabel ?: "unknown"
                    val score    = pred?.riskScore
                    val emoji = when (category.lowercase()) {
                        "casual"   -> "✅"
                        "at_risk"  -> "⚠️"
                        "addicted" -> "🔴"
                        else       -> "🎮"
                    }
                    val riskLine = RiskPresentation.scopedRiskText(
                        "This session",
                        category,
                        score
                    )
                    showSessionEndNotification(gameName, "$emoji $riskLine")
                }
                resp.code() in 400..499 && resp.code() != 408 && resp.code() != 429 -> {
                    // Permanent reject (e.g. 404 — the session no longer exists server-side).
                    // Nothing to retry; clear locally so detection can resume.
                    prefs.clearSession()
                    stopService(Intent(this, GameMonitorService::class.java))
                }
                // else: 5xx / 408 / 429 — the end did NOT persist. Keep the local session so
                // a later tick retries (re-adoption restarts the grace), instead of leaving
                // the server session open. No clearSession() here.
                else -> ensureGameMonitorService()
            }
        } catch (_: Exception) {
            // Network failure — the request never landed. Keep the session and retry on a
            // later tick rather than clearing locally while the server still shows it open.
            ensureGameMonitorService()
        }
    }

    /** Keep behavioral/voice monitoring attached whenever a transient end failure leaves
     * the local session alive. Safe to call if the service is already running. */
    private fun ensureGameMonitorService() {
        if (!prefs.canMonitor() || !prefs.hasActiveSession()) return
        try {
            ContextCompat.startForegroundService(
                this,
                Intent(this, GameMonitorService::class.java).apply {
                    putExtra("session_id", prefs.activeSessionId)
                    putExtra("game_name", prefs.activeSessionGame)
                    putExtra("user_id", prefs.userId)
                    putExtra("server_url", prefs.serverUrl)
                }
            )
        } catch (e: Exception) {
            android.util.Log.w("PassiveMonitor", "Could not attach session monitor: ${e.message}")
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
            .setContentText(riskLine)
            .setAutoCancel(true)
            .setContentIntent(intent)
            .build()
        val nm = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        nm.notify(Constants.NOTIF_SESSION_END, notif)
    }
}
