package com.pes.gamingdetector.activities

import android.Manifest
import android.app.AppOpsManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.widget.EditText
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivityHomeBinding
import com.pes.gamingdetector.services.AdminReceiver
import com.pes.gamingdetector.services.GameMonitorService
import com.pes.gamingdetector.services.GameNotificationService
import com.pes.gamingdetector.services.PassiveMonitorService
import com.pes.gamingdetector.services.VoiceRecorderService
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.PrivacyText
import kotlinx.coroutines.launch

class HomeActivity : AppCompatActivity() {
    private lateinit var binding: ActivityHomeBinding
    private lateinit var prefs: PrefsManager

    // The single in-flight permission dialog, so prompts never stack on top of each
    // other and the box closes itself the moment everything is granted.
    private var permDialog: AlertDialog? = null

    // Runtime-permission prompt (microphone + notifications). Registered up-front;
    // whatever the user chooses, we then continue to the special-access checks.
    private val runtimePerms = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ -> checkRequiredPermissions() }

    private val uiHandler = Handler(Looper.getMainLooper())
    private val TODAY_REFRESH_MS = 12_000L      // how often Home re-pulls today's snapshot (instant-feel)
    private val bannerRefresh = object : Runnable {
        override fun run() {
            refreshBanner()
            uiHandler.postDelayed(this, 3_000L)
        }
    }

    // Re-pull today's snapshot periodically (incl. a freshly parent-set limit) so the home
    // screen updates on its own — previously it only refreshed in onResume(), so a limit
    // change showed up only after navigating away and back.
    private val todayRefresh = object : Runnable {
        override fun run() {
            loadToday()
            uiHandler.postDelayed(this, TODAY_REFRESH_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityHomeBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = "Hi, ${prefs.userName}"

        // Monitoring only starts after parental consent for the CURRENT policy
        // version. A bumped CONSENT_VERSION (policy changed) re-triggers consent
        // even on a device that previously agreed to an older version.
        if (consentCurrent()) {
            startMonitoring()
            syncConsentIfPending()   // catch up if an earlier grant never reached the server
        } else {
            ensureConsent()
        }

        binding.btnResume.setOnClickListener {
            if (prefs.hasActiveSession()) {
                startActivity(Intent(this, SessionActivity::class.java))
            }
        }

        binding.btnDashboard.setOnClickListener {
            startActivity(Intent(this, ChildDashboardActivity::class.java))
        }

        // Interactive break (a healthy alternative to "one more game").
        binding.cardBreak.setOnClickListener {
            startActivity(Intent(this, BreatheActivity::class.java))
        }
        binding.btnShuffle.setOnClickListener { shuffleActivity() }
        shuffleActivity()
    }

    override fun onResume() {
        super.onResume()
        refreshBanner()
        loadToday()
        uiHandler.postDelayed(bannerRefresh, 3_000L)
        uiHandler.postDelayed(todayRefresh, TODAY_REFRESH_MS)
        if (consentCurrent()) checkRequiredPermissions()
    }

    /** Self-awareness snapshot: how much the child has played today vs a healthy goal,
        their streak, and an encouraging line. One call, refreshed on every resume. */
    private fun loadToday() {
        lifecycleScope.launch {
            try {
                val resp = ApiClient.getInstance(prefs.serverUrl).getChildEnriched(prefs.userId)
                val b = resp.body()
                if (resp.isSuccessful && b?.success == true) {
                    val played = b.playedTodayHours ?: 0.0
                    val goal   = (b.dailyGoalHours ?: 2.0).coerceAtLeast(0.1)
                    val over   = b.goalIsParentSet == true && played >= goal
                    // Only touch a view when its value actually changed, so the periodic
                    // refresh leaves the screen perfectly still unless something updated
                    // (e.g. a freshly parent-set limit) — no flicker / jitter.
                    fun upd(tv: TextView, s: String) { if (tv.text?.toString() != s) tv.text = s }

                    upd(binding.tvTodayHours, "${"%.1f".format(played)}h played today")
                    val pct = ((played / goal) * 100).toInt().coerceIn(0, 100)
                    if (binding.todayProgress.progress != pct) binding.todayProgress.progress = pct
                    upd(binding.tvTodayGoal, when {
                        over                      -> "Over your ${"%.1f".format(goal)}h limit — time for a break"
                        b.goalIsParentSet == true -> "of your ${"%.1f".format(goal)}h daily limit"
                        else                      -> "of a healthy ~${"%.1f".format(goal)}h a day"
                    })
                    binding.tvTodayGoal.setTextColor(
                        getColor(if (over) R.color.risk_high else R.color.text_secondary))
                    val streak = b.streak?.currentStreak ?: 0
                    upd(binding.tvStreak, if (streak > 0)
                        "🔥 $streak-day healthy streak"
                    else
                        "🌱 Stay under your goal to start a healthy streak")
                    upd(binding.tvSelfAwareness, b.selfAwarenessMessage ?: "")
                }
            } catch (_: Exception) { /* offline — keep last values */ }
        }
    }

    private val tryInstead = listOf(
        "Go for a 10-minute walk 🚶",
        "Drink a glass of water 💧",
        "Stretch or do 10 push-ups 💪",
        "Message a friend to hang out 👋",
        "Read a few pages of a book 📖",
        "Step outside for some fresh air 🌳",
        "Draw or doodle something ✏️",
        "Help out at home — surprise your family 🧹",
        "Play a song you love 🎵",
        "Plan something fun for the weekend 🗓️",
    )
    private fun shuffleActivity() {
        binding.tvActivity.text = tryInstead.random()
    }

    /** Start always-on passive monitoring (auto-session detection + screen events). */
    private fun startMonitoring() {
        ContextCompat.startForegroundService(
            this, Intent(this, PassiveMonitorService::class.java)
        )
        requestRuntimePermissions()
    }

    /** Ask directly (system dialog) for the runtime permissions — microphone (voice
        analysis) and notifications (Android 13+) — then fall through to the
        special-access prompts. Only asks for ones not already granted. */
    private fun requestRuntimePermissions() {
        val needed = mutableListOf<String>()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            needed += Manifest.permission.RECORD_AUDIO
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            needed += Manifest.permission.POST_NOTIFICATIONS
        }
        if (needed.isNotEmpty()) {
            runtimePerms.launch(needed.toTypedArray())   // continues in the callback
        } else {
            checkRequiredPermissions()
        }
    }

    /** True only when consent was given for the version of the policy this build
        ships. A newer CONSENT_VERSION (policy changed) makes this false → re-prompt. */
    private fun consentCurrent() =
        prefs.consentDone && prefs.consentVersion == PrivacyText.CONSENT_VERSION

    /** Gate monitoring behind parental consent. Honours consent already recorded
        server-side (e.g. after a reinstall); otherwise shows a blocking dialog. */
    private fun ensureConsent() {
        val uid = prefs.userId
        lifecycleScope.launch {
            var needs = true
            try {
                val resp = ApiClient.getInstance(prefs.serverUrl).getConsent(uid)
                if (resp.isSuccessful) needs = resp.body()?.needsConsent ?: true
            } catch (_: Exception) { /* offline — show consent to be safe */ }
            if (!needs) {
                // Server already holds consent → local state is authoritative AND synced.
                prefs.consentDone = true
                prefs.consentVersion = PrivacyText.CONSENT_VERSION
                prefs.consentSynced = true
                startMonitoring()
            } else {
                showConsentDialog()
            }
        }
    }

    private fun showConsentDialog() {
        AlertDialog.Builder(this)
            .setTitle("Parental Monitoring Consent")
            .setMessage(PrivacyText.CONSENT_SUMMARY)
            .setCancelable(false)
            .setNegativeButton("Decline") { _, _ ->
                Toast.makeText(this, "Monitoring requires consent. Exiting.", Toast.LENGTH_LONG).show()
                finishAffinity()
            }
            .setPositiveButton("I Agree") { _, _ -> grantConsent() }
            .show()
    }

    private fun grantConsent() {
        val uid = prefs.userId
        lifecycleScope.launch {
            var synced = false
            try {
                val resp = ApiClient.getInstance(prefs.serverUrl)
                    .postConsent(mapOf("user_id" to uid, "version" to PrivacyText.CONSENT_VERSION))
                synced = resp.isSuccessful
            } catch (_: Exception) { /* offline — re-synced on a later launch (see below) */ }
            prefs.consentDone = true
            prefs.consentVersion = PrivacyText.CONSENT_VERSION
            // The parent's consent is a recorded fact the SERVER must hold (audit trail).
            // If the POST didn't land, remember that so we retry — previously the local
            // flag alone made consentCurrent() true and the server was never told.
            prefs.consentSynced = synced
            startMonitoring()
        }
    }

    /** Re-send consent to the server if a previous grant didn't reach it (offline at the
     *  time). Cheap no-op once synced. */
    private fun syncConsentIfPending() {
        if (!prefs.consentDone || prefs.consentSynced) return
        val uid = prefs.userId
        lifecycleScope.launch {
            try {
                val resp = ApiClient.getInstance(prefs.serverUrl)
                    .postConsent(mapOf("user_id" to uid, "version" to prefs.consentVersion))
                if (resp.isSuccessful) prefs.consentSynced = true
            } catch (_: Exception) { /* still offline — try again next launch */ }
        }
    }

    override fun onPause() {
        super.onPause()
        uiHandler.removeCallbacks(bannerRefresh)
        uiHandler.removeCallbacks(todayRefresh)
    }

    override fun onDestroy() {
        super.onDestroy()
        permDialog?.dismiss()
        permDialog = null
    }

    private fun refreshBanner() {
        if (prefs.hasActiveSession()) {
            binding.resumeBanner.visibility = View.VISIBLE
            binding.tvResumegame.text = "Session active: ${prefs.activeSessionGame}"
        } else {
            binding.resumeBanner.visibility = View.GONE
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_home, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_settings -> {
            requireParentPin("open settings") {
                startActivity(Intent(this, SettingsActivity::class.java))
            }
            true
        }
        R.id.action_logout -> {
            requireParentPin("log out") { logoutChild() }
            true
        }
        else -> super.onOptionsItemSelected(item)
    }

    /** Gate a sensitive action (logout / settings) behind the family parent PIN, verified
     *  server-side — the child never knows the PIN, so they can't quietly stop monitoring. */
    private fun requireParentPin(action: String, onSuccess: () -> Unit) {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
            hint = "Parent PIN"
        }
        AlertDialog.Builder(this)
            .setTitle("Parent PIN required")
            .setMessage("Ask your parent to enter their PIN to $action.")
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("Unlock") { _, _ ->
                val pin = input.text?.toString()?.trim().orEmpty()
                if (pin.isEmpty()) {
                    Toast.makeText(this, "Enter the parent PIN", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                lifecycleScope.launch {
                    val ok = try {
                        val resp = ApiClient.getInstance(prefs.serverUrl)
                            .verifyParentPin(mapOf("user_id" to prefs.userId, "pin" to pin))
                        resp.isSuccessful && resp.body()?.valid == true
                    } catch (_: Exception) { false }
                    if (ok) onSuccess()
                    else Toast.makeText(this@HomeActivity,
                        "Incorrect parent PIN", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** Sign out cleanly: stop the monitoring services and close any open server
        session (while the token is still valid) before clearing the login. Otherwise
        logout left orphaned foreground services running and a session open server-side
        (no end_time → skewed duration/behaviour). */
    private fun logoutChild() {
        stopService(Intent(this, PassiveMonitorService::class.java))
        stopService(Intent(this, GameMonitorService::class.java))
        stopService(Intent(this, VoiceRecorderService::class.java))
        val sid = prefs.activeSessionId
        val uid = prefs.userId          // capture before logout() clears it
        lifecycleScope.launch {
            if (sid != -1) {
                try { ApiClient.getInstance(prefs.serverUrl).endSession(sid) } catch (_: Exception) {}
            }
            // Tell the parent the child signed out — while the token is still valid.
            if (uid != -1) {
                try {
                    ApiClient.getInstance(prefs.serverUrl)
                        .reportTamper(mapOf("user_id" to uid, "event" to "logout"))
                } catch (_: Exception) {}
            }
            prefs.logout()
            startActivity(Intent(this@HomeActivity, LoginActivity::class.java))
            finishAffinity()
        }
    }

    // --- Permission helpers ---

    private fun checkRequiredPermissions() {
        // Show dialogs one at a time in priority order; each "Skip" moves to the next.
        // Re-run on every resume, so returning from Settings advances to the next
        // missing permission — or closes the box entirely once all are granted.
        when {
            !hasUsageStatsPermission() -> showPermissionDialog(
                title = "Allow Usage Access",
                message = "This lets the app detect which game you're playing and start tracking automatically — no manual tapping needed.\n\nTap 'Open Settings', find this app in the list, and toggle it ON.",
                settingsIntent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS),
                onSkip = { if (!isNotificationListenerEnabled()) showNotifListenerDialog() else showAccessibilityDialog() }
            )
            !isNotificationListenerEnabled() -> showNotifListenerDialog()
            !isAccessibilityEnabled() -> showAccessibilityDialog()
            // Device Admin + battery exemption are offered BEFORE the keyboard steps, and
            // each is offered once (flag set when shown). They used to sit AFTER the
            // keyboard checks, so a child who never set up the custom keyboard left the
            // chain stuck on the keyboard prompt and NEVER saw the device-admin offer
            // (it only appeared on a later launch once the keyboard happened to be set).
            // The anti-uninstall protection is too important to be gated behind an
            // optional keyboard, so it now reliably appears during first setup.
            (!isDeviceAdminActive() && !prefs.deviceAdminOffered) -> {
                prefs.deviceAdminOffered = true     // optional + offered once, so it doesn't nag
                showDeviceAdminDialog()
            }
            (!isBatteryExempt() && !prefs.batteryExemptOffered) -> {
                prefs.batteryExemptOffered = true   // ask once; declining shouldn't nag
                showBatteryExemptDialog()
            }
            !isCustomKeyboardEnabled() -> showKeyboardEnableDialog()
            !isCustomKeyboardSelected() -> showKeyboardSelectDialog()
            else -> dismissPermDialog()   // everything granted → close any lingering box
        }
    }

    /** Already exempt from Doze/battery optimisation? Aggressive OEM power managers
     *  killing the always-on monitor is the top real-world cause of silent monitoring. */
    private fun isBatteryExempt(): Boolean {
        val pm = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun showBatteryExemptDialog() {
        if (isFinishing || isDestroyed) return
        permDialog?.dismiss()
        permDialog = AlertDialog.Builder(this)
            .setTitle("Keep monitoring running")
            .setMessage("Some phones aggressively close background apps to save battery, " +
                "which silently stops gaming monitoring. Allow this app to ignore battery " +
                "optimisation so monitoring stays reliable.")
            .setCancelable(false)
            .setPositiveButton("Allow") { _, _ ->
                try {
                    startActivity(Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        android.net.Uri.parse("package:$packageName")))
                } catch (_: Exception) {
                    // Some OEMs hide the direct prompt — fall back to the list screen.
                    try {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    } catch (_: Exception) {}
                }
            }
            .setNegativeButton("Skip") { _, _ -> advanceToKeyboardStep() }
            .show()
    }

    private fun isDeviceAdminActive(): Boolean {
        val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
        return dpm.isAdminActive(ComponentName(this, AdminReceiver::class.java))
    }

    private fun showDeviceAdminDialog() {
        if (isFinishing || isDestroyed) return
        permDialog?.dismiss()
        permDialog = AlertDialog.Builder(this)
            .setTitle("Protect monitoring from removal (optional)")
            .setMessage("Make this app a device administrator so it can't be casually " +
                "uninstalled, and your parent is alerted the instant someone tries to turn " +
                "it off. You can skip this.")
            .setCancelable(false)
            .setPositiveButton("Enable") { _, _ ->
                try {
                    val intent = Intent(android.app.admin.DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN)
                        .putExtra(android.app.admin.DevicePolicyManager.EXTRA_DEVICE_ADMIN,
                            ComponentName(this, AdminReceiver::class.java))
                        .putExtra(android.app.admin.DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                            "Keeps gaming-wellbeing monitoring active and alerts your parent if it's turned off.")
                    startActivity(intent)
                } catch (_: Exception) {}
            }
            // Continue to the next setup step on skip so the chain never dead-ends here.
            .setNegativeButton("Skip") { _, _ ->
                if (!isBatteryExempt() && !prefs.batteryExemptOffered) {
                    prefs.batteryExemptOffered = true
                    showBatteryExemptDialog()
                } else advanceToKeyboardStep()
            }
            .show()
    }

    /** Advance the permission chain to whichever keyboard step is still outstanding. */
    private fun advanceToKeyboardStep() {
        when {
            !isCustomKeyboardEnabled() -> showKeyboardEnableDialog()
            !isCustomKeyboardSelected() -> showKeyboardSelectDialog()
            else -> dismissPermDialog()
        }
    }

    private fun dismissPermDialog() {
        permDialog?.dismiss()
        permDialog = null
    }

    private fun showNotifListenerDialog() {
        showPermissionDialog(
            title = "Allow Notification Access",
            message = "Tracks gaming app notifications so the app can detect cravings and urges.\n\nTap 'Open Settings', find this app, and toggle it ON.",
            settingsIntent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS),
            onSkip = { if (!isAccessibilityEnabled()) showAccessibilityDialog() }
        )
    }

    private fun showAccessibilityDialog() {
        showPermissionDialog(
            title = "Allow Accessibility Access",
            message = "Captures chat messages sent during gaming sessions to detect toxic language and emotional stress.\n\nTap 'Open Settings', find 'GamingDetector', and toggle it ON.",
            settingsIntent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS),
            onSkip = { advanceAfterAccessibility() }
        )
    }

    /** Skip-chain mirror of the post-accessibility order in checkRequiredPermissions:
     *  device admin → battery → keyboard. Keeps the manual "Skip" path from bypassing the
     *  device-admin offer (the bug where it only appeared after a later re-login). */
    private fun advanceAfterAccessibility() {
        when {
            (!isDeviceAdminActive() && !prefs.deviceAdminOffered) -> {
                prefs.deviceAdminOffered = true
                showDeviceAdminDialog()
            }
            (!isBatteryExempt() && !prefs.batteryExemptOffered) -> {
                prefs.batteryExemptOffered = true
                showBatteryExemptDialog()
            }
            else -> advanceToKeyboardStep()
        }
    }

    private fun showKeyboardEnableDialog() {
        showPermissionDialog(
            title = "Enable the Wellbeing Keyboard",
            message = "Some games (like Roblox) draw their chat box inside the game itself, where other tools can't read it. This app's own keyboard captures what's typed there reliably — and only the child's own typing, never other players' messages.\n\nTap 'Open Settings', then turn ON 'Gaming Wellbeing Keyboard'.",
            settingsIntent = Intent(Settings.ACTION_INPUT_METHOD_SETTINGS),
            onSkip = { if (!isCustomKeyboardSelected()) showKeyboardSelectDialog() else dismissPermDialog() }
        )
    }

    private fun showKeyboardSelectDialog() {
        if (isFinishing || isDestroyed) return
        permDialog?.dismiss()
        permDialog = AlertDialog.Builder(this)
            .setTitle("Switch to the Wellbeing Keyboard")
            .setMessage("Almost done — now set it as the active keyboard so typed in-game chat is captured.\n\nTap 'Choose Keyboard' and pick 'Gaming Wellbeing Keyboard'.")
            .setCancelable(false)
            .setPositiveButton("Choose Keyboard") { _, _ ->
                try {
                    (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
                        .showInputMethodPicker()
                } catch (_: Exception) {}
            }
            .setNegativeButton("Skip") { _, _ -> dismissPermDialog() }
            .show()
    }

    private fun showPermissionDialog(
        title: String,
        message: String,
        settingsIntent: Intent,
        onSkip: (() -> Unit)?
    ) {
        if (isFinishing || isDestroyed) return
        // Replace any existing dialog so prompts never stack.
        permDialog?.dismiss()
        permDialog = AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setCancelable(false)
            .setPositiveButton("Open Settings") { _, _ ->
                try { startActivity(settingsIntent) } catch (_: Exception) {}
            }
            .setNegativeButton("Skip") { _, _ -> onSkip?.invoke() }
            .show()
    }

    private fun hasUsageStatsPermission(): Boolean {
        val ops = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ops.unsafeCheckOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), packageName
            )
        } else {
            @Suppress("DEPRECATION")
            ops.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), packageName
            )
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun isNotificationListenerEnabled(): Boolean {
        return try {
            val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
                ?: ""
            val myComponent = ComponentName(this, GameNotificationService::class.java).flattenToString()
            flat.split(":").any { it == myComponent }
        } catch (_: Exception) { false }
    }

    private fun isAccessibilityEnabled(): Boolean {
        return try {
            val flat = Settings.Secure.getString(
                contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
            ) ?: ""
            flat.contains(packageName, ignoreCase = true)
        } catch (_: Exception) { false }
    }

    /** Our custom keyboard is in the device's list of enabled input methods.
     *  Uses InputMethodManager, NOT Settings.Secure.ENABLED_INPUT_METHODS — that key
     *  throws SecurityException for apps targeting SDK > 33 (Android 12+), which would
     *  crash this check on every modern device. */
    private fun isCustomKeyboardEnabled(): Boolean = try {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.enabledInputMethodList.any { it.packageName == packageName }
    } catch (_: Exception) { false }

    /** Our custom keyboard is the currently-selected (active) input method.
     *  DEFAULT_INPUT_METHOD is still readable, but wrap defensively so a future
     *  restriction degrades to "re-prompt" rather than crashing the app. */
    private fun isCustomKeyboardSelected(): Boolean {
        return try {
            val default = Settings.Secure.getString(
                contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD
            ) ?: ""
            default.contains(packageName, ignoreCase = true)
        } catch (_: Exception) { false }
    }

}
