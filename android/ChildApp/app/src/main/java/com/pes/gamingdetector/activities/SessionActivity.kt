package com.pes.gamingdetector.activities

import android.Manifest
import android.app.AppOpsManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.StartSessionRequest
import com.pes.gamingdetector.R
import com.pes.gamingdetector.databinding.ActivitySessionBinding
import com.pes.gamingdetector.services.GameMonitorService
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class SessionActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySessionBinding
    private lateinit var prefs: PrefsManager
    private var timerJob: Job? = null
    private var livePredictJob: Job? = null
    private var gameName: String = ""

    private val audioPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, "Microphone permission needed for voice analysis", Toast.LENGTH_LONG).show()
        }
        checkUsageStatsAndStart()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySessionBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        gameName = intent.getStringExtra("game_name") ?: prefs.activeSessionGame

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = gameName

        if (prefs.hasActiveSession()) {
            showActiveSession()
        } else {
            showPreSession()
        }

        binding.btnStartSession.setOnClickListener { checkPermissionsAndStart() }
        binding.btnEndSession.setOnClickListener { confirmEndSession() }
        binding.btnDashboard.setOnClickListener {
            startActivity(Intent(this, ChildDashboardActivity::class.java))
        }
    }

    private fun showPreSession() {
        binding.layoutPreSession.visibility = View.VISIBLE
        binding.layoutActiveSession.visibility = View.GONE
        binding.layoutResult.visibility = View.GONE
    }

    private fun showActiveSession() {
        binding.layoutPreSession.visibility = View.GONE
        binding.layoutActiveSession.visibility = View.VISIBLE
        binding.layoutResult.visibility = View.GONE
        binding.tvGameName.text = gameName
        startTimer()
        startLivePredictions()
    }

    private fun checkPermissionsAndStart() {
        if (!isAccessibilityServiceEnabled()) {
            AlertDialog.Builder(this)
                .setTitle("Enable Chat Capture")
                .setMessage("To analyse your in-game chat, enable 'Gaming Detector' in Accessibility Settings.\n\nTap 'Open Settings', find 'Gaming Detector' and turn it ON, then come back.")
                .setPositiveButton("Open Settings") { _, _ ->
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }
                .setNegativeButton("Skip") { _, _ -> checkAudioPermission() }
                .show()
        } else {
            checkAudioPermission()
        }
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val service = "$packageName/${com.pes.gamingdetector.services.ChatAccessibilityService::class.java.canonicalName}"
        return try {
            val enabled = android.provider.Settings.Secure.getString(
                contentResolver, android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
            ) ?: return false
            enabled.split(":").any { it.equals(service, ignoreCase = true) }
        } catch (_: Exception) { false }
    }

    private fun checkAudioPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            audioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        } else {
            checkUsageStatsAndStart()
        }
    }

    private fun checkUsageStatsAndStart() {
        if (!hasUsageStatsPermission()) {
            AlertDialog.Builder(this)
                .setTitle("Usage Access Required")
                .setMessage("Grant Usage Access to detect which game you're playing.")
                .setPositiveButton("Open Settings") { _, _ ->
                    startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                }
                .setNegativeButton("Skip") { _, _ -> startSession() }
                .show()
        } else {
            startSession()
        }
    }

    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(APP_OPS_SERVICE) as AppOpsManager
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            appOps.unsafeCheckOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), packageName
            )
        } else {
            @Suppress("DEPRECATION")
            appOps.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), packageName
            )
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun startSession() {
        binding.btnStartSession.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.startSession(
                    StartSessionRequest(userId = prefs.userId, gameName = gameName)
                )
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val sessionId = resp.body()!!.sessionId
                    prefs.activeSessionId = sessionId
                    prefs.activeSessionGame = gameName
                    prefs.activeSessionStart = System.currentTimeMillis()

                    startMonitorService(sessionId)
                    showActiveSession()
                } else {
                    Toast.makeText(this@SessionActivity, "Failed to start session", Toast.LENGTH_SHORT).show()
                    binding.btnStartSession.isEnabled = true
                }
            } catch (e: Exception) {
                Toast.makeText(this@SessionActivity, "Server error: ${e.message}", Toast.LENGTH_LONG).show()
                binding.btnStartSession.isEnabled = true
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun startMonitorService(sessionId: Int) {
        val intent = Intent(this, GameMonitorService::class.java).apply {
            putExtra("session_id", sessionId)
            putExtra("game_name", gameName)
            putExtra("user_id", prefs.userId)
            putExtra("server_url", prefs.serverUrl)
        }
        ContextCompat.startForegroundService(this, intent)
    }

    private fun confirmEndSession() {
        AlertDialog.Builder(this)
            .setTitle("End Session?")
            .setMessage("This will stop monitoring and generate your risk report.")
            .setPositiveButton("End") { _, _ -> endSession() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun endSession() {
        timerJob?.cancel()
        livePredictJob?.cancel()
        binding.btnEndSession.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE

        val sessionId = prefs.activeSessionId

        stopService(Intent(this, GameMonitorService::class.java))

        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.endSession(sessionId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val pred = resp.body()!!.prediction
                    prefs.clearSession()
                    if (pred != null) showResult(pred)
                    else {
                        Toast.makeText(this@SessionActivity, "Session ended", Toast.LENGTH_SHORT).show()
                        finish()
                    }
                }
            } catch (e: Exception) {
                Toast.makeText(this@SessionActivity, "Error ending session: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun showResult(pred: com.pes.gamingdetector.api.Prediction) {
        binding.layoutActiveSession.visibility = View.GONE
        binding.layoutResult.visibility = View.VISIBLE

        binding.tvRiskLabel.text = pred.riskLabel.uppercase()
        binding.tvRiskScore.text = "Score: ${"%.0f".format(pred.riskScore * 100)}%"
        binding.tvBehaviorScore.text = "Behavior: ${"%.0f".format(pred.behaviorScore * 100)}%"
        binding.tvChatScore.text = "Chat: ${"%.0f".format(pred.chatScore * 100)}%"
        binding.tvVoiceScore.text = "Voice: ${"%.0f".format(pred.voiceScore * 100)}%"

        binding.tvRiskLabel.setTextColor(android.graphics.Color.WHITE)

        // Observation period notice
        var noteShown = false
        if (pred.observationMode == true) {
            val done = pred.sessionsAnalyzed ?: 0
            binding.tvObservationNote.text =
                "Building baseline — $done of 3 sessions done. Results improve with more sessions."
            noteShown = true
        }
        if (!pred.shortSessionNote.isNullOrBlank()) {
            binding.tvObservationNote.text = pred.shortSessionNote
            noteShown = true
        }
        binding.cardObservationNote.visibility = if (noteShown) View.VISIBLE else View.GONE

        // Top contributing factors
        val factors = pred.topFactors
        if (!factors.isNullOrEmpty()) {
            val sb = StringBuilder()
            factors.forEachIndexed { i, f ->
                if (i > 0) sb.append("\n")
                sb.append("• ${f.label}: ${"%.1f".format(f.value)} (${"%.0f".format(f.contributionPct)}% impact)")
            }
            binding.tvTopFactors.text = sb.toString()
            binding.cardTopFactors.visibility = View.VISIBLE
        } else {
            binding.cardTopFactors.visibility = View.GONE
        }
    }

    private fun startTimer() {
        timerJob = lifecycleScope.launch {
            while (isActive) {
                val elapsed = System.currentTimeMillis() - prefs.activeSessionStart
                val h = elapsed / 3_600_000
                val m = (elapsed % 3_600_000) / 60_000
                val s = (elapsed % 60_000) / 1_000
                binding.tvTimer.text = "%02d:%02d:%02d".format(h, m, s)
                delay(1_000)
            }
        }
    }

    private fun startLivePredictions() {
        var nudgeSentAt90  = false
        var nudgeSentAt120 = false

        livePredictJob = lifecycleScope.launch {
            while (isActive) {
                // Break nudge notifications
                val elapsed = System.currentTimeMillis() - prefs.activeSessionStart
                val elapsedMin = elapsed / 60_000
                if (elapsedMin >= 90 && !nudgeSentAt90) {
                    nudgeSentAt90 = true
                    sendBreakNudge("90-Minute Check-in",
                        "You've been gaming for 90 minutes. Take a 10-minute break — your brain will thank you!")
                } else if (elapsedMin >= 120 && !nudgeSentAt120) {
                    nudgeSentAt120 = true
                    sendBreakNudge("2-Hour Reminder",
                        "2 hours of gaming done! Time to take a proper break and rest your eyes.")
                }

                try {
                    val api  = ApiClient.getInstance(prefs.serverUrl)
                    val resp = api.livePrediction(prefs.activeSessionId)
                    if (resp.isSuccessful && resp.body()?.success == true) {
                        val body  = resp.body()!!
                        val label = body.riskLabel ?: "—"
                        val score = body.riskScore?.let { "${"%.0f".format(it * 100)}%" } ?: ""
                        binding.tvLiveRisk.text = "Live: $label $score"
                    }
                } catch (_: Exception) {}

                // Delay AFTER the fetch so the first prediction shows immediately
                // rather than after a 60-second blank stretch.
                delay(60_000)
            }
        }
    }

    private fun sendBreakNudge(title: String, message: String) {
        try {
            val notif = NotificationCompat.Builder(this, Constants.CHANNEL_MONITORING)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(this).notify(System.currentTimeMillis().toInt(), notif)
        } catch (_: SecurityException) {}
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    override fun onDestroy() {
        timerJob?.cancel()
        livePredictJob?.cancel()
        super.onDestroy()
    }
}
