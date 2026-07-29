package com.pes.parentmonitor.activities

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import com.github.mikephil.charting.components.LimitLine
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.data.*
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.github.mikephil.charting.formatter.ValueFormatter
import com.pes.parentmonitor.R
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.ParentalDashboard
import com.pes.parentmonitor.api.RiskThresholds
import com.pes.parentmonitor.api.TrendPoint
import com.pes.parentmonitor.databinding.ActivityParentalDashboardBinding
import com.pes.parentmonitor.service.AlertPollingService
import com.pes.parentmonitor.util.AlertCounts
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.RiskPresentation
import com.pes.parentmonitor.util.SessionManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.roundToInt

class ParentalDashboardActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityParentalDashboardBinding
    private lateinit var prefs: PrefsManager

    private val uiHandler = Handler(Looper.getMainLooper())
    // Foreground auto-refresh cadence. Silent (no spinner/animation) and a no-op when the
    // payload is unchanged, so a tighter interval just makes the numbers + live "playing
    // now" strip feel near-instant without the parent pulling to refresh.
    private val DASH_REFRESH_MS = 15_000L
    private val dashRefresh = object : Runnable {
        override fun run() {
            loadDashboard(silent = true)   // background tick: no spinner, no chart re-animation
            uiHandler.postDelayed(this, DASH_REFRESH_MS)
        }
    }
    // Last payload actually rendered — a silent tick that returns identical data is a no-op,
    // so the screen (and the chart) stays perfectly still unless something really changed.
    private var lastDash: ParentalDashboard? = null
    private var dashboardJob: Job? = null
    private var dashboardGeneration = 0
    private var displayedChildId = -1

    private val notifPermLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* polling still works */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityParentalDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return

        requestNotificationPermissionIfNeeded()
        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = "Parent Dashboard"

        binding.swipeRefresh.setOnRefreshListener { loadDashboard() }

        binding.btnAlerts.setOnClickListener {
            startActivity(Intent(this, AlertsActivity::class.java))
        }
        binding.btnRecommendations.setOnClickListener {
            startActivity(Intent(this, RecommendationsActivity::class.java))
        }
        binding.btnNudge.setOnClickListener { showNudgeDialog() }
        binding.btnEmotions.setOnClickListener {
            startActivity(Intent(this, EmotionInsightsActivity::class.java))
        }
        binding.btnChatAnalysis.setOnClickListener {
            startActivity(Intent(this, ChatAnalysisActivity::class.java))
        }
        binding.btnWeeklyReport.setOnClickListener {
            startActivity(Intent(this, WeeklyReportActivity::class.java))
        }
        binding.btnDownloadPdf.setOnClickListener { downloadPdfReport() }
        binding.btnSetLimit.setOnClickListener { showSetLimitDialog() }

        startAlertPolling()
        // First load happens in onResume (which always runs right after onCreate) —
        // avoids a redundant double fetch + double spinner on launch.
    }

    override fun onAuthenticatedResume() {
        loadDashboard()
        uiHandler.postDelayed(dashRefresh, DASH_REFRESH_MS)
    }

    override fun onPause() {
        super.onPause()
        uiHandler.removeCallbacks(dashRefresh)
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
        ) {
            notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun startAlertPolling() {
        val intent = Intent(this, AlertPollingService::class.java).apply {
            putExtra("parent_id", prefs.parentId)
            putExtra("child_user_id", prefs.childUserId)
            putExtra("server_url", prefs.serverUrl)
        }
        ContextCompat.startForegroundService(this, intent)
    }

    // ── Send a nudge to the child (pops up as a notification on their phone) ──
    private fun showNudgeDialog() {
        val presets = arrayOf(
            "Time to take a break 🙂",
            "Please wrap up this game",
            "Mind your language, please",
            "Dinner's ready — pause the game",
            "Write your own…"
        )
        AlertDialog.Builder(this)
            .setTitle("Send a nudge to your child")
            .setItems(presets) { _, which ->
                if (which == presets.lastIndex) showCustomNudgeInput()
                else sendNudge(presets[which])
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showCustomNudgeInput() {
        val input = EditText(this).apply { hint = "Your message" }
        AlertDialog.Builder(this)
            .setTitle("Custom nudge")
            .setView(input)
            .setPositiveButton("Send") { _, _ ->
                val msg = input.text.toString().trim()
                if (msg.isNotEmpty()) sendNudge(msg)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun sendNudge(message: String) {
        val childId = prefs.childUserId
        if (childId == -1) {
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show(); return
        }
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.sendNudge(mapOf("user_id" to childId, "message" to message))
                val ok   = resp.isSuccessful && resp.body()?.success == true
                Toast.makeText(this@ParentalDashboardActivity,
                    if (ok) "Nudge sent to your child 👍" else "Couldn't send nudge",
                    Toast.LENGTH_SHORT).show()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@ParentalDashboardActivity, "Network error", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun loadDashboard(silent: Boolean = false) {
        if (silent && dashboardJob?.isActive == true) return
        if (!silent) dashboardJob?.cancel()
        val generation = ++dashboardGeneration
        // Bind this request to the child selected NOW. A slow response for child A must not
        // overwrite the screen after the parent has switched to child B (the fetch is async
        // and childUserId is mutable), which showed one child's data under another's name.
        val reqChild = prefs.childUserId
        val reqServer = prefs.serverUrl
        prepareDashboardForChild(reqChild)
        if (!silent) binding.progressBar.visibility = View.VISIBLE
        if (reqChild <= 0) {
            binding.progressBar.visibility = View.GONE
            binding.swipeRefresh.isRefreshing = false
            if (!silent) Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        dashboardJob = lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(reqServer)
                val resp = api.getParentalDashboard(reqChild)
                if (generation != dashboardGeneration) return@launch
                if (reqChild != prefs.childUserId) return@launch   // selection changed mid-flight — drop
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val body = resp.body()!!
                    // On a silent background tick, if nothing changed, leave the UI entirely
                    // untouched (no re-render, no chart rebuild) — the dashboard stays still.
                    if (silent && body == lastDash) return@launch
                    lastDash = body
                    renderDashboard(body, animate = !silent)
                } else if (!silent) {
                    Toast.makeText(
                        this@ParentalDashboardActivity,
                        "Dashboard data is unavailable (${resp.code()})",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // Don't interrupt the user with a toast on a silent background tick.
                if (!silent) {
                    val msg = if (e is java.io.IOException)
                        "Cannot reach server at $reqServer — go to Settings and verify the address."
                    else "Load failed: ${e.message}"
                    Toast.makeText(this@ParentalDashboardActivity, msg, Toast.LENGTH_LONG).show()
                }
            } finally {
                if (generation == dashboardGeneration) {
                    if (!silent) binding.progressBar.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
                    dashboardJob = null
                }
            }
        }
    }

    /**
     * Remove the previous sibling's payload before starting a request for the newly
     * selected child. A failed/slow request must never leave child A's risk under child B.
     */
    private fun prepareDashboardForChild(childId: Int) {
        if (displayedChildId == childId) return
        displayedChildId = childId
        lastDash = null

        binding.tvChildName.text = prefs.childName.ifBlank { "Your Child" }
        binding.tvCurrentRisk.text = "Unknown"
        binding.tvRiskScore.text = "—"
        binding.tvRiskPeriod.text = "Waiting for daily risk data"
        binding.tvRiskPeriod.visibility = View.VISIBLE
        binding.riskIndicatorBar.setBackgroundColor(getColor(R.color.text_secondary))
        binding.tvCurrentRisk.setTextColor(android.graphics.Color.WHITE)
        binding.tvWeeklyHours.text = "—"
        binding.tvLateNight.text = "—"
        binding.btnAlerts.text = "Alerts"
        binding.tvObservationBanner.visibility = View.GONE
        binding.tvLiveStatus.visibility = View.GONE
        binding.cardAnomaly.visibility = View.GONE
        binding.tvRecommendationPreview.text = ""
        binding.tvRecommendationPreview.visibility = View.GONE
        binding.cardTimeLimitSuggestion.visibility = View.GONE
        binding.cardPeerComparison.visibility = View.GONE
        binding.cardSleepImpact.visibility = View.GONE
        binding.cardRiskExplanation.visibility = View.GONE
        binding.cardStreak.visibility = View.GONE
        binding.btnSetLimit.text = "Set Daily Limit"
        setupTrendChart(emptyList(), animate = false)
        setupTopGamesText(emptyList(), emptyList())
    }

    private fun renderDashboard(dash: ParentalDashboard, animate: Boolean = true) {
        binding.tvChildName.text = dash.childName ?: "Your Child"

        // Optional cards default to hidden every render. The per-card blocks below only ever
        // switched them ON, so after switching to a child who lacks a given signal (no peer
        // data, no sleep data, …) the PREVIOUS child's card stayed on screen.
        binding.cardTimeLimitSuggestion.visibility = View.GONE
        binding.cardPeerComparison.visibility = View.GONE
        binding.cardSleepImpact.visibility = View.GONE
        binding.cardRiskExplanation.visibility = View.GONE
        binding.cardStreak.visibility = View.GONE

        if (dash.observationMode == true) {
            val done = dash.sessionsAnalyzed ?: 0
            binding.tvObservationBanner.text =
                "Building baseline — $done of 3 sessions completed. Predictions become more accurate with more data."
            binding.tvObservationBanner.visibility = View.VISIBLE
        } else {
            binding.tvObservationBanner.visibility = View.GONE
        }

        val risk  = dash.currentRisk
        val score = dash.riskScore
        // Screening label (e.g. "High concern") rather than the clinical category key.
        binding.tvCurrentRisk.text  = RiskPresentation.displayLabel(risk, dash.riskLabel)
        binding.tvRiskScore.text    = RiskPresentation.scoreText(score)

        // The headline is a per-day roll-up — say so, so a 2-hour day and a 2-minute day
        // aren't read as the same "current risk".
        val period = dash.riskPeriod
        val periodText = RiskPresentation.periodText(period?.label, period?.sessions)
        if (periodText != null) {
            binding.tvRiskPeriod.text = periodText
            binding.tvRiskPeriod.visibility = View.VISIBLE
        } else {
            binding.tvRiskPeriod.visibility = View.GONE
        }

        // ── Live status strip: playing-now + monitoring heartbeat health ──
        val liveBits = mutableListOf<String>()
        dash.liveStatus?.let { ls ->
            if (ls.isPlaying) {
                val mins = ls.sessionDurationMins
                liveBits += "🎮 Playing ${ls.currentGame ?: "a game"} now" +
                    (mins?.let { " · ${it} min" } ?: "")
            }
        }
        dash.monitoring?.let { m ->
            val mins = m.minutesSinceCheckin
            liveBits += when {
                m.online == true       -> "🟢 Monitoring active"
                mins != null           -> "🔴 No check-in for " +
                    (if (mins >= 120) "${mins / 60}h" else "${mins}m") +
                    " — phone may be off or app closed"
                else                   -> "🔴 Monitoring not checking in"
            }
            // Tamper-protection level, so the parent KNOWS whether an uninstall attempt
            // would alert them instantly (Device Admin) or only via the ~15-min watchdog.
            // Only shown while the app is checking in — when monitoring is offline the
            // flag is whatever the LAST heartbeat said (possibly right before an
            // uninstall), and "offline but protected" would be a contradiction.
            if (m.online == true) {
                when (m.protected) {
                    true  -> liveBits += "🛡️ Uninstall-protected"
                    false -> liveBits += "⚠️ Not uninstall-protected — enable Device Admin on the child phone"
                    null  -> { /* unknown (older child app) — say nothing */ }
                }
                // Recorder state is session-specific. Idle between games is not a
                // degradation, so show it only while a game is actually active.
                if (dash.liveStatus?.isPlaying == true) when (m.voiceCapture) {
                    true -> liveBits += "🎙️ Voice capture active"
                    false -> liveBits += "⚠️ Voice capture unavailable — Android may block background microphone start; use the available behavior/chat signals"
                    null -> liveBits += "ℹ️ Voice capture status unknown for this session"
                }
                // Capture-permission health: the app can be RUNNING yet collecting nothing
                // useful if the child revoked a permission. Name which capability is off so
                // the parent can fix it, rather than trusting a green "Monitoring active".
                if (m.online == true) {
                    val off = mutableListOf<String>()
                    if (m.permUsage == false)         off += "game detection"
                    if (m.permAccessibility == false) off += "chat capture"
                    if (m.permKeyboard == false)      off += "in-game keyboard"
                    if (off.isNotEmpty()) {
                        liveBits += "⚠️ Monitoring degraded — ${off.joinToString(", ")} off on the child phone " +
                            "(re-enable in the Child app)"
                    }
                }
            }
        }
        if (liveBits.isNotEmpty()) {
            binding.tvLiveStatus.text = liveBits.joinToString("   ")
            binding.tvLiveStatus.visibility = View.VISIBLE
        } else {
            binding.tvLiveStatus.visibility = View.GONE
        }

        val color = when (risk?.lowercase()) {
            "casual"   -> getColor(R.color.risk_low)
            "at_risk"  -> getColor(R.color.risk_medium)
            "addicted" -> getColor(R.color.risk_high)
            else       -> getColor(R.color.text_secondary)
        }
        // Risk indicator is in the gradient header — keep white text, color only the bar
        binding.tvCurrentRisk.setTextColor(android.graphics.Color.WHITE)
        binding.riskIndicatorBar.setBackgroundColor(color)

        binding.tvWeeklyHours.text = "${"%.1f".format(dash.totalHoursWeek ?: 0.0)}h"
        binding.tvLateNight.text   = "${dash.lateNightCount ?: 0}"

        // Anomaly alert card
        val anomaly = dash.topAnomaly
        if (anomaly != null) {
            binding.cardAnomaly.visibility = View.VISIBLE
            binding.tvAnomalyMessage.text = anomaly.message
        } else {
            binding.cardAnomaly.visibility = View.GONE
        }

        val alerts     = dash.alerts ?: emptyList()
        val unreadCount = AlertCounts.unread(dash.unreadAlertCount, alerts)
        binding.btnAlerts.text = if (unreadCount > 0) "Alerts ($unreadCount)" else "Alerts"

        setupTrendChart(dash.trendData.orEmpty(), animate, dash.riskThresholds)
        setupTopGamesText(dash.topGames.orEmpty(), dash.recentGames)

        val rec = dash.recommendations ?: emptyList()
        if (rec.isNotEmpty()) {
            binding.tvRecommendationPreview.text       = rec.firstOrNull() ?: ""
            binding.tvRecommendationPreview.visibility = View.VISIBLE
        } else {
            binding.tvRecommendationPreview.text = ""
            binding.tvRecommendationPreview.visibility = View.GONE
        }

        // Notification dedup is driven by durable alert ids, not by comparing this
        // daily roll-up with a latest-session category. Keeping those scopes separate
        // prevents false "risk changed" notifications when their bands differ.

        // ── Time limit suggestion ──────────────────────────────
        binding.cardTimeLimitSuggestion.visibility = View.GONE
        dash.timeLimitSuggestion?.let { tl ->
            binding.cardTimeLimitSuggestion.visibility = View.VISIBLE
            binding.tvSuggestedLimit.text = "${tl.suggestedDailyHours}h / day"
            binding.tvLimitReason.text    = tl.reason
            val urgencyColor = when (tl.urgency) {
                "high"   -> getColor(R.color.risk_high)
                "medium" -> getColor(R.color.risk_medium)
                else     -> getColor(R.color.risk_low)
            }
            binding.tvLimitUrgency.text = tl.urgency.uppercase()
            binding.tvLimitUrgency.setBackgroundColor(urgencyColor)

            // If parent already set a limit, update button text
            dash.parentSetLimit?.let { set ->
                binding.btnSetLimit.text = "Set This Limit (current: ${set}h)"
            } ?: run {
                binding.btnSetLimit.text = "Set This Limit"
            }
        }

        // ── Peer comparison ────────────────────────────────────
        binding.cardPeerComparison.visibility = View.GONE
        dash.peerComparison?.let { pc ->
            binding.cardPeerComparison.visibility = View.VISIBLE
            // percentile = "plays more than X% of peers", so X=90 is the TOP 10%. Label it
            // as the Nth percentile, not "Top 90%" (which read as the opposite).
            binding.tvPeerPercentile.text = "${pc.percentile}th %ile"
            binding.tvPeerMessage.text    = pc.message
            val pcColor = when (pc.level) {
                "very_high" -> getColor(R.color.risk_high)
                "high"      -> getColor(R.color.risk_medium)
                else        -> getColor(R.color.risk_low)
            }
            binding.tvPeerPercentile.setTextColor(pcColor)
        }

        // ── Sleep impact ───────────────────────────────────────
        binding.cardSleepImpact.visibility = View.GONE
        dash.sleepImpact?.let { si ->
            if (si.available == true) {
                binding.cardSleepImpact.visibility = View.VISIBLE
                binding.tvLateNightPct.text        = "${si.lateNightPercent ?: 0}%"
                binding.tvSleepDisruption.text     = "${si.sleepDisruptionDays ?: 0} days"
                binding.tvSleepMessage.text        = si.message ?: ""
            }
        }

        // ── Explainable risk + which signals were analysed ─────
        val factors = dash.riskExplanation ?: emptyList()
        val sig = dash.latestSignals
        binding.cardRiskExplanation.visibility = View.GONE
        if (factors.isNotEmpty() || sig != null) {
            binding.cardRiskExplanation.visibility = View.VISIBLE
            val sb = StringBuilder()
            if (factors.isNotEmpty()) {
                sb.append("Latest completed-session factors (may differ from the daily headline):\n")
            }
            factors.forEach { f ->
                // SHAP direction: ▲ raises the score, ▼ lowers it.
                val arrow = when (f.direction) { "raises" -> "▲"; "lowers" -> "▼"; else -> "•" }
                sb.append("$arrow ${f.label}:  ${"%.1f".format(f.value)}  (${f.contributionPct.toInt()}%)\n")
            }
            // Be explicit about which signals fed this score. A signal marked
            // "not captured" means the game produced no data for it (e.g. no in-game
            // text chat, or a silent session) — so a 0 there isn't a clean result,
            // it's an absent one, and the score relied on the remaining signals.
            if (sig != null) {
                fun mark(b: Boolean?) = when (b) {
                    true -> "✓ analysed"
                    false -> "— not captured"
                    null -> "? availability unknown"
                }
                if (sb.isNotEmpty()) sb.append("\n")
                sb.append("Daily roll-up signal availability:\n")
                sb.append("• Behaviour: ${mark(sig.behavior)}\n")
                sb.append("• Chat: ${mark(sig.chat)}\n")
                sb.append("• Voice: ${mark(sig.voice)}\n")
                if (sig.chat == false || sig.voice == false) {
                    sb.append("Some games have no in-game text chat or voice; the score then relies only on the signals that were available.\n")
                } else if (sig.chat == null || sig.voice == null || sig.behavior == null) {
                    sb.append("Signal availability was not reported for every source; unknown does not mean absent or clean.\n")
                }
            }
            dash.disclaimer?.let { sb.append("\nℹ ${it}") }
            binding.tvRiskExplanation.text = sb.toString().trimEnd()
        }

        // ── Healthy streak ─────────────────────────────────────
        binding.cardStreak.visibility = View.GONE
        dash.streak?.let { s ->
            binding.cardStreak.visibility = View.VISIBLE
            binding.tvStreakCurrent.text  = "${s.currentStreak} days"
            binding.tvStreakBest.text     = "${s.longestStreak} days"
            binding.tvStreakTotal.text    = "${s.totalHealthyDays}"
        }
    }

    private fun showSetLimitDialog() {
        val editText = EditText(this).apply {
            hint = "Daily limit in hours (e.g. 2.0)"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            setPadding(48, 24, 48, 24)
        }
        AlertDialog.Builder(this)
            .setTitle("Set Daily Time Limit")
            .setMessage("Enter a daily gaming limit for ${prefs.childName.ifBlank { "your child" }}:")
            .setView(editText)
            .setPositiveButton("Set Limit") { _, _ ->
                val hours = editText.text.toString().toDoubleOrNull()
                if (hours == null || hours < 0.5 || hours > 24) {
                    Toast.makeText(this, "Enter a number between 0.5 and 24 hours", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                lifecycleScope.launch {
                    try {
                        val api  = ApiClient.getInstance(prefs.serverUrl)
                        val resp = api.setTimeLimit(mapOf("user_id" to prefs.childUserId, "daily_limit_hours" to hours))
                        if (resp.isSuccessful) {
                            Toast.makeText(this@ParentalDashboardActivity,
                                "Limit set to ${hours}h/day", Toast.LENGTH_SHORT).show()
                            loadDashboard()
                        }
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        Toast.makeText(this@ParentalDashboardActivity,
                            "Failed to set limit: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun downloadPdfReport() {
        val childId = prefs.childUserId
        val childName = prefs.childName
        val serverUrl = prefs.serverUrl
        if (childId <= 0) {
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(serverUrl)
                val resp = api.downloadWeeklyReportPdf(childId)
                if (resp.isSuccessful && resp.body() != null) {
                    val bytes = withContext(Dispatchers.IO) { resp.body()!!.bytes() }
                    val file  = File(cacheDir, "gaming_report_$childId.pdf")
                    withContext(Dispatchers.IO) { file.writeBytes(bytes) }

                    val uri = FileProvider.getUriForFile(
                        this@ParentalDashboardActivity,
                        "${packageName}.fileprovider",
                        file
                    )
                    val shareIntent = Intent(Intent.ACTION_SEND).apply {
                        type = "application/pdf"
                        putExtra(Intent.EXTRA_STREAM, uri)
                        putExtra(Intent.EXTRA_SUBJECT, "Gaming Health Report — $childName")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    startActivity(Intent.createChooser(shareIntent, "Share PDF Report"))
                } else {
                    Toast.makeText(this@ParentalDashboardActivity,
                        "PDF not available on server", Toast.LENGTH_SHORT).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@ParentalDashboardActivity,
                    "Download failed: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun setupTrendChart(
        trendData: List<TrendPoint>,
        animate: Boolean = true,
        thresholds: RiskThresholds? = null
    ) {
        val suppliedSome = thresholds?.someConcern
            ?.takeIf { it.isFinite() && it in 0.0..1.0 }
        val suppliedHigh = thresholds?.highConcern
            ?.takeIf { it.isFinite() && it in 0.0..1.0 }
        val (someCutoff, highCutoff) =
            if (suppliedSome != null && suppliedHigh != null && suppliedSome < suppliedHigh) {
                suppliedSome to suppliedHigh
            } else {
                // Older servers did not expose their configured thresholds.
                0.33 to 0.67
            }
        val somePct = (someCutoff * 100).roundToInt()
        val highPct = (highCutoff * 100).roundToInt()
        binding.tvTrendCaption.text =
            "Daily risk score (0–100%, vertical) per day (date, horizontal). " +
            "Some concern begins at $somePct%; High concern begins at $highPct%."

        if (trendData.isEmpty()) {
            binding.lineChart.clear()
            binding.lineChart.invalidate()
            return
        }
        val points  = trendData.takeLast(14)
        val entries = points.mapIndexed { i, p -> Entry(i.toFloat(), (p.score * 100).toFloat()) }
        val labels  = points.map { it.date.takeLast(5) }
        val dataSet = LineDataSet(entries, "Risk (%)").apply {
            color = getColor(R.color.colorPrimary)
            setCircleColor(getColor(R.color.colorPrimary))
            lineWidth    = 2.5f
            circleRadius = 4f
            setDrawValues(false)
            mode      = LineDataSet.Mode.CUBIC_BEZIER
            fillColor = getColor(R.color.colorPrimary)
            setDrawFilled(true)
            fillAlpha = 30
        }
        binding.lineChart.apply {
            data = LineData(dataSet)
            // X axis: the date of each day (MM-DD), along the bottom.
            xAxis.apply {
                valueFormatter     = IndexAxisValueFormatter(labels)
                granularity        = 1f
                labelRotationAngle = -45f
                position           = XAxis.XAxisPosition.BOTTOM
                setDrawGridLines(false)
                textColor          = getColor(R.color.text_primary)   // dark = clearly visible
                textSize           = 10f
                setAvoidFirstLastClipping(true)
            }
            extraBottomOffset = 18f   // room for the rotated date labels (was clipped)
            // Y axis: 0–100% with the risk-band cutoffs drawn in, so the line is read
            // against "some concern" (33%) and "high concern" (67%).
            axisLeft.apply {
                axisMinimum = 0f
                axisMaximum = 100f
                granularity = 25f
                textColor   = getColor(R.color.text_secondary)
                valueFormatter = object : ValueFormatter() {
                    override fun getFormattedValue(value: Float) = "${value.toInt()}%"
                }
                removeAllLimitLines()
                addLimitLine(LimitLine((someCutoff * 100).toFloat(), "Some concern").apply {
                    lineColor = getColor(R.color.risk_medium); lineWidth = 1.2f
                    textColor = getColor(R.color.risk_medium); textSize = 9f
                })
                addLimitLine(LimitLine((highCutoff * 100).toFloat(), "High concern").apply {
                    lineColor = getColor(R.color.risk_high); lineWidth = 1.2f
                    textColor = getColor(R.color.risk_high); textSize = 9f
                })
            }
            axisRight.isEnabled   = false
            legend.isEnabled      = false
            description.isEnabled = false
            setTouchEnabled(true)
            if (animate) animateX(800)
            invalidate()
        }
    }

    private fun setupTopGamesText(
        topGames: List<com.pes.parentmonitor.api.TopGame>,
        recentGames: List<com.pes.parentmonitor.api.RecentGame>?
    ) {
        val sb = StringBuilder()
        if (topGames.isEmpty()) {
            sb.append("No game data yet")
        } else {
            sb.append("Most played (by hours):\n")
            topGames.take(5).forEachIndexed { i, g ->
                sb.append("${i + 1}. ${g.game} — ${"%.1f".format(g.hours)} hrs (${g.sessions} sessions)\n")
            }
        }
        // Recently played surfaces brand-new / short sessions that rank below the top-5.
        val recent = recentGames.orEmpty().filter { !it.game.isNullOrBlank() }
        if (recent.isNotEmpty()) {
            sb.append("\nRecently played:\n")
            recent.take(5).forEach { g ->
                val mins = g.minutes ?: 0.0
                val played = mins.let {
                    if (it >= 60) "${"%.1f".format(it / 60)} hrs" else "${it.toInt()} min"
                }
                sb.append("• ${g.game} — $played total\n")
            }
        }
        binding.tvTopGames.text = sb.toString().trimEnd()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_parent, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_switch_child -> {
            switchChild()
            true
        }
        R.id.action_settings -> {
            startActivity(Intent(this, SettingsActivity::class.java))
            true
        }
        R.id.action_logout -> {
            doLogout()
            true
        }
        else -> super.onOptionsItemSelected(item)
    }

    /** Sign out cleanly: stop the sticky poller (it would otherwise keep "Guardian Active"
     *  running and notifying about the last child indefinitely) and deregister this
     *  device's push token (so a logged-out phone stops receiving the family's alerts),
     *  THEN clear the session. */
    private fun doLogout() {
        SessionManager.logout(this, prefs)
        AuthNavigation.openLogin(this)
    }

    /** Switch to another child in the same family WITHOUT re-entering the family code —
     *  the bearer token already authorizes the family's children. */
    private fun switchChild() {
        lifecycleScope.launch {
            val list = try {
                val resp = ApiClient.getInstance(prefs.serverUrl).getChildren()
                if (resp.isSuccessful) resp.body()?.children.orEmpty() else emptyList()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                emptyList()
            }
            when {
                list.isEmpty() ->
                    Toast.makeText(this@ParentalDashboardActivity,
                        "Couldn't load your children", Toast.LENGTH_SHORT).show()
                list.size == 1 ->
                    Toast.makeText(this@ParentalDashboardActivity,
                        "This family has only one child", Toast.LENGTH_SHORT).show()
                else -> {
                    val names = list.map { c ->
                        if (c.userId == prefs.childUserId) "${c.name}  ✓" else c.name
                    }.toTypedArray()
                    AlertDialog.Builder(this@ParentalDashboardActivity)
                        .setTitle("Switch child")
                        .setItems(names) { _, which ->
                            val chosen = list[which]
                            if (chosen.userId != prefs.childUserId) {
                                prefs.childUserId = chosen.userId
                                prefs.childName   = chosen.name
                                // Clear child A synchronously; child B's request may be
                                // slow or fail and must not leave A's data visible.
                                prepareDashboardForChild(chosen.userId)
                                // Re-target the background poller too — otherwise it
                                // keeps notifying about the PREVIOUS child until the
                                // app is killed and restarted.
                                startAlertPolling()
                                loadDashboard()
                            }
                        }
                        .setNegativeButton("Cancel", null)
                        .show()
                }
            }
        }
    }
}
