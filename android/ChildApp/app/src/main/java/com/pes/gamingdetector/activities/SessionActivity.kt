package com.pes.gamingdetector.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivitySessionBinding
import com.pes.gamingdetector.services.GameMonitorService
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Live view of the CURRENT auto-detected session: timer, live risk, an "End Session"
 * button, and the result screen after ending. Sessions are started automatically by
 * PassiveMonitorService, so there is no manual "start" here — this screen is only
 * reached while a session is already active (the resume banner or the monitoring
 * notification). If it's opened without one, it just returns to Home.
 */
class SessionActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySessionBinding
    private lateinit var prefs: PrefsManager
    private var timerJob: Job? = null
    private var livePredictJob: Job? = null
    private var gameName: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySessionBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        gameName = intent.getStringExtra("game_name") ?: prefs.activeSessionGame

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = gameName

        // Sessions start automatically; this screen only views an active one.
        if (!prefs.hasActiveSession()) {
            finish()
            return
        }
        showActiveSession()

        binding.btnEndSession.setOnClickListener { confirmEndSession() }
        binding.btnDashboard.setOnClickListener {
            startActivity(Intent(this, ChildDashboardActivity::class.java))
        }
    }

    private fun showActiveSession() {
        binding.layoutActiveSession.visibility = View.VISIBLE
        binding.layoutResult.visibility = View.GONE
        binding.tvGameName.text = gameName
        startTimer()
        startLivePredictions()
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
        // Break-reminder nudges live in GameMonitorService so they fire during real
        // gameplay (when this screen isn't open); here we only show the live risk.
        livePredictJob = lifecycleScope.launch {
            while (isActive) {
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
