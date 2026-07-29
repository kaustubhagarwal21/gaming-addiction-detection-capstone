package com.pes.gamingdetector.activities

import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivitySessionBinding
import com.pes.gamingdetector.services.GameMonitorService
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.RiskPresentation
import com.pes.gamingdetector.util.SessionDurationClock
import kotlinx.coroutines.CancellationException
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
class SessionActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivitySessionBinding
    private lateinit var prefs: PrefsManager
    private var timerJob: Job? = null
    private var livePredictJob: Job? = null
    private var gameName: String = ""
    private var displayedSessionId: Int = -1
    private var durationClock: SessionDurationClock? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!ensureAuthenticatedOnCreate()) return
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
        displayedSessionId = prefs.activeSessionId
        durationClock = SessionDurationClock(
            sessionStartedAtEpochMs = prefs.activeSessionStart,
            createdAtEpochMs = System.currentTimeMillis(),
            createdAtElapsedMs = SystemClock.elapsedRealtime(),
        )
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

        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.endSession(sessionId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val pred = resp.body()!!.prediction
                    prefs.clearSession()
                    stopService(Intent(this@SessionActivity, GameMonitorService::class.java))
                    if (pred != null) showResult(pred)
                    else {
                        Toast.makeText(this@SessionActivity, "Session ended", Toast.LENGTH_SHORT).show()
                        finish()
                    }
                } else if (resp.code() in 400..499 && resp.code() != 408 && resp.code() != 429) {
                    // The server definitively rejected this id (usually an already-pruned
                    // session). Retrying forever cannot recover it; clear local state.
                    prefs.clearSession()
                    stopService(Intent(this@SessionActivity, GameMonitorService::class.java))
                    Toast.makeText(this@SessionActivity,
                        "Session is no longer active on the server.", Toast.LENGTH_LONG).show()
                    finish()
                } else {
                    // Server error — without this branch the button stayed disabled
                    // forever with no message. Restore the live view so the child can
                    // retry (the passive monitor will also auto-end it later).
                    Toast.makeText(this@SessionActivity,
                        "Couldn't end the session (server ${resp.code()}) — try again.",
                        Toast.LENGTH_LONG).show()
                    restoreActiveView()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@SessionActivity, "Error ending session: ${e.message}", Toast.LENGTH_LONG).show()
                restoreActiveView()
            } finally {
                if (isActive && !isFinishing && !isDestroyed) {
                    binding.progressBar.visibility = View.GONE
                }
            }
        }
    }

    /** Re-arm the live session screen after a failed end attempt. */
    private fun restoreActiveView() {
        binding.btnEndSession.isEnabled = true
        if (prefs.hasActiveSession()) {
            // Ending used to stop GameMonitor before the network call. A timeout/5xx then
            // left the session active but silently disabled voice/break monitoring.
            restartMonitorService()
            startTimer()
            startLivePredictions()
        }
    }

    private fun restartMonitorService() {
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
        } catch (_: Exception) {
            // The visible activity is normally eligible to start it; leave the session
            // retryable even on an OEM-specific refusal.
        }
    }

    private fun showResult(pred: com.pes.gamingdetector.api.Prediction) {
        binding.layoutActiveSession.visibility = View.GONE
        binding.layoutResult.visibility = View.VISIBLE

        binding.tvRiskLabel.text = RiskPresentation.displayLabel(pred.riskLabel)
        binding.tvRiskScore.text =
            "This session \u00B7 ${RiskPresentation.riskScoreText(pred.riskScore)}"
        fun signalText(label: String, present: Boolean?, score: Double): String =
            if (present == false) "$label: not captured"
            else "$label: ${"%.0f".format(score * 100)}%"
        binding.tvBehaviorScore.text = signalText(
            "Behavior", pred.modalities?.behavior, pred.behaviorScore)
        binding.tvChatScore.text = signalText(
            "Chat", pred.modalities?.chat, pred.chatScore)
        binding.tvVoiceScore.text = signalText(
            "Voice", pred.modalities?.voice, pred.voiceScore)

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

    /** The passive monitor can auto-end the session while this screen is open (game
     *  closed, grace expired). Detect that and close the live view gracefully — the
     *  timer would otherwise show elapsed-since-epoch garbage and the live poller
     *  would query session id -1. */
    private fun sessionEndedElsewhere(): Boolean {
        if (prefs.hasActiveSession() && prefs.activeSessionId == displayedSessionId) return false
        timerJob?.cancel()
        livePredictJob?.cancel()
        Toast.makeText(this, "Session ended", Toast.LENGTH_SHORT).show()
        finish()
        return true
    }

    private fun startTimer() {
        timerJob = lifecycleScope.launch {
            while (isActive) {
                if (sessionEndedElsewhere()) return@launch
                val elapsed = durationClock?.elapsedMs(SystemClock.elapsedRealtime()) ?: 0L
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
                if (sessionEndedElsewhere()) return@launch
                try {
                    val api  = ApiClient.getInstance(prefs.serverUrl)
                    val resp = api.livePrediction(prefs.activeSessionId)
                    if (resp.isSuccessful && resp.body()?.success == true) {
                        val body  = resp.body()!!
                        binding.tvLiveRisk.text = RiskPresentation.scopedRiskText(
                            "Live session",
                            body.riskLabel,
                            body.riskScore
                        )
                    }
                } catch (e: CancellationException) {
                    throw e
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
