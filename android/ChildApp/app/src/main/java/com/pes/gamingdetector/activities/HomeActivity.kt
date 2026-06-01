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
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.Game
import com.pes.gamingdetector.databinding.ActivityHomeBinding
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
    private val bannerRefresh = object : Runnable {
        override fun run() {
            refreshBanner()
            uiHandler.postDelayed(this, 3_000L)
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
        } else {
            ensureConsent()
        }

        binding.rvGames.layoutManager = GridLayoutManager(this, 2)

        binding.btnResume.setOnClickListener {
            if (prefs.hasActiveSession()) {
                startActivity(Intent(this, SessionActivity::class.java))
            }
        }

        binding.btnDashboard.setOnClickListener {
            startActivity(Intent(this, ChildDashboardActivity::class.java))
        }

        loadGames()
    }

    override fun onResume() {
        super.onResume()
        refreshBanner()
        uiHandler.postDelayed(bannerRefresh, 3_000L)
        if (consentCurrent()) checkRequiredPermissions()
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
                prefs.consentDone = true
                prefs.consentVersion = PrivacyText.CONSENT_VERSION
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
            try {
                ApiClient.getInstance(prefs.serverUrl)
                    .postConsent(mapOf("user_id" to uid, "version" to PrivacyText.CONSENT_VERSION))
            } catch (_: Exception) { /* recorded locally; will retry on next launch */ }
            prefs.consentDone = true
            prefs.consentVersion = PrivacyText.CONSENT_VERSION
            startMonitoring()
        }
    }

    override fun onPause() {
        super.onPause()
        uiHandler.removeCallbacks(bannerRefresh)
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

    private fun loadGames() {
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getGames()
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val games = resp.body()!!.games
                    // Read-only list of monitored games — sessions start automatically
                    // when a game is opened, so tapping a tile does nothing.
                    binding.rvGames.adapter = GameAdapter(games)
                }
            } catch (e: Exception) {
                val msg = if (e is java.io.IOException)
                    "Cannot reach server at ${prefs.serverUrl} — go to Settings and update the server address."
                else "Failed to load games: ${e.message}"
                Toast.makeText(this@HomeActivity, msg, Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_home, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_settings -> {
            startActivity(Intent(this, SettingsActivity::class.java))
            true
        }
        R.id.action_logout -> {
            logoutChild()
            true
        }
        else -> super.onOptionsItemSelected(item)
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
        lifecycleScope.launch {
            if (sid != -1) {
                try { ApiClient.getInstance(prefs.serverUrl).endSession(sid) } catch (_: Exception) {}
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
            else -> dismissPermDialog()   // everything granted → close any lingering box
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
            onSkip = null
        )
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
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
            ?: return false
        val myComponent = ComponentName(this, GameNotificationService::class.java).flattenToString()
        return flat.split(":").any { it == myComponent }
    }

    private fun isAccessibilityEnabled(): Boolean {
        val flat = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        return flat.contains(packageName, ignoreCase = true)
    }

    private inner class GameAdapter(
        private val games: List<Game>
    ) : RecyclerView.Adapter<GameAdapter.VH>() {

        inner class VH(v: View) : RecyclerView.ViewHolder(v) {
            val tvName: TextView = v.findViewById(R.id.tvGameName)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val v = layoutInflater.inflate(R.layout.item_game, parent, false)
            return VH(v)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            holder.tvName.text = games[position].name
        }

        override fun getItemCount() = games.size
    }
}
