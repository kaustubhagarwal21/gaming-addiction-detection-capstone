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
import androidx.appcompat.app.AppCompatActivity
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
import com.pes.parentmonitor.api.TrendPoint
import com.pes.parentmonitor.databinding.ActivityParentalDashboardBinding
import com.pes.parentmonitor.service.AlertPollingService
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

class ParentalDashboardActivity : AppCompatActivity() {
    private lateinit var binding: ActivityParentalDashboardBinding
    private lateinit var prefs: PrefsManager

    private val uiHandler = Handler(Looper.getMainLooper())
    private val dashRefresh = object : Runnable {
        override fun run() {
            loadDashboard(silent = true)   // background tick: no spinner, no chart re-animation
            uiHandler.postDelayed(this, 30_000L)
        }
    }

    private val notifPermLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* polling still works */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityParentalDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

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

    override fun onResume() {
        super.onResume()
        loadDashboard()
        uiHandler.postDelayed(dashRefresh, 30_000L)
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
        startService(intent)
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
            } catch (e: Exception) {
                Toast.makeText(this@ParentalDashboardActivity, "Network error", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun loadDashboard(silent: Boolean = false) {
        if (!silent) binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getParentalDashboard(prefs.childUserId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    renderDashboard(resp.body()!!, animate = !silent)
                }
            } catch (e: Exception) {
                // Don't interrupt the user with a toast on a silent background tick.
                if (!silent) {
                    val msg = if (e is java.io.IOException)
                        "Cannot reach server at ${prefs.serverUrl} — go to Settings and verify the address."
                    else "Load failed: ${e.message}"
                    Toast.makeText(this@ParentalDashboardActivity, msg, Toast.LENGTH_LONG).show()
                }
            } finally {
                if (!silent) binding.progressBar.visibility = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun renderDashboard(dash: ParentalDashboard, animate: Boolean = true) {
        binding.tvChildName.text = dash.childName ?: "Your Child"

        if (dash.observationMode == true) {
            val done = dash.sessionsAnalyzed ?: 0
            binding.tvObservationBanner.text =
                "Building baseline — $done of 3 sessions completed. Predictions become more accurate with more data."
            binding.tvObservationBanner.visibility = View.VISIBLE
        } else {
            binding.tvObservationBanner.visibility = View.GONE
        }

        val risk  = dash.currentRisk ?: "unknown"
        val score = dash.riskScore ?: 0.0
        // Screening label (e.g. "High concern") rather than the clinical category key.
        binding.tvCurrentRisk.text  = (dash.riskLabel ?: risk.replace("_", " ")
            .replaceFirstChar { it.uppercase() })
        binding.tvRiskScore.text    = "${"%.0f".format(score * 100)}%"

        // The headline is a per-day roll-up — say so, so a 2-hour day and a 2-minute day
        // aren't read as the same "current risk".
        val period = dash.riskPeriod
        if (period?.label != null) {
            val n = period.sessions ?: 0
            binding.tvRiskPeriod.text = "${period.label} · $n ${if (n == 1) "session" else "sessions"}"
            binding.tvRiskPeriod.visibility = View.VISIBLE
        } else {
            binding.tvRiskPeriod.visibility = View.GONE
        }

        val color = when (risk.lowercase()) {
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
        val unreadCount = alerts.count { !it.read }
        binding.btnAlerts.text = if (unreadCount > 0) "Alerts ($unreadCount)" else "Alerts"

        dash.trendData?.let { setupTrendChart(it, animate) }
        dash.topGames?.let  { setupTopGamesText(it, dash.recentGames) }

        val rec = dash.recommendations ?: emptyList()
        if (rec.isNotEmpty()) {
            binding.tvRecommendationPreview.text       = rec.firstOrNull() ?: ""
            binding.tvRecommendationPreview.visibility = View.VISIBLE
        }

        prefs.lastRiskLevel = risk

        // ── Time limit suggestion ──────────────────────────────
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
        dash.peerComparison?.let { pc ->
            binding.cardPeerComparison.visibility = View.VISIBLE
            binding.tvPeerPercentile.text = "Top ${pc.percentile}%"
            binding.tvPeerMessage.text    = pc.message
            val pcColor = when (pc.level) {
                "very_high" -> getColor(R.color.risk_high)
                "high"      -> getColor(R.color.risk_medium)
                else        -> getColor(R.color.risk_low)
            }
            binding.tvPeerPercentile.setTextColor(pcColor)
        }

        // ── Sleep impact ───────────────────────────────────────
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
        if (factors.isNotEmpty() || sig != null) {
            binding.cardRiskExplanation.visibility = View.VISIBLE
            val sb = StringBuilder()
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
                fun mark(b: Boolean?) = if (b == true) "✓ analysed" else "— not captured"
                if (sb.isNotEmpty()) sb.append("\n")
                val sigHdr = dash.riskPeriod?.label?.let { "Signals analysed ($it):" }
                    ?: "Signals used for this score:"
                sb.append("$sigHdr\n")
                sb.append("• Behaviour: ${mark(sig.behavior)}\n")
                sb.append("• Chat: ${mark(sig.chat)}\n")
                sb.append("• Voice: ${mark(sig.voice)}\n")
                if (sig.chat != true || sig.voice != true) {
                    sb.append("Some games have no in-game text chat or voice; the score then relies only on the signals that were available.\n")
                }
            }
            dash.disclaimer?.let { sb.append("\nℹ ${it}") }
            binding.tvRiskExplanation.text = sb.toString().trimEnd()
        }

        // ── Healthy streak ─────────────────────────────────────
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
                if (hours == null || hours < 0 || hours > 24) {
                    Toast.makeText(this, "Enter a valid number between 0 and 24", Toast.LENGTH_SHORT).show()
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
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.downloadWeeklyReportPdf(prefs.childUserId)
                if (resp.isSuccessful && resp.body() != null) {
                    val bytes = withContext(Dispatchers.IO) { resp.body()!!.bytes() }
                    val file  = File(cacheDir, "gaming_report_${prefs.childUserId}.pdf")
                    withContext(Dispatchers.IO) { file.writeBytes(bytes) }

                    val uri = FileProvider.getUriForFile(
                        this@ParentalDashboardActivity,
                        "${packageName}.fileprovider",
                        file
                    )
                    val shareIntent = Intent(Intent.ACTION_SEND).apply {
                        type = "application/pdf"
                        putExtra(Intent.EXTRA_STREAM, uri)
                        putExtra(Intent.EXTRA_SUBJECT, "Gaming Health Report — ${prefs.childName}")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    startActivity(Intent.createChooser(shareIntent, "Share PDF Report"))
                } else {
                    Toast.makeText(this@ParentalDashboardActivity,
                        "PDF not available on server", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@ParentalDashboardActivity,
                    "Download failed: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun setupTrendChart(trendData: List<TrendPoint>, animate: Boolean = true) {
        if (trendData.isEmpty()) return
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
                addLimitLine(LimitLine(33f, "Some concern").apply {
                    lineColor = getColor(R.color.risk_medium); lineWidth = 1.2f
                    textColor = getColor(R.color.risk_medium); textSize = 9f
                })
                addLimitLine(LimitLine(67f, "High concern").apply {
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
            prefs.logout()
            startActivity(Intent(this, LoginActivity::class.java))
            finishAffinity()
            true
        }
        else -> super.onOptionsItemSelected(item)
    }

    /** Switch to another child in the same family WITHOUT re-entering the family code —
     *  the bearer token already authorizes the family's children. */
    private fun switchChild() {
        lifecycleScope.launch {
            val list = try {
                val resp = ApiClient.getInstance(prefs.serverUrl).getChildren()
                if (resp.isSuccessful) resp.body()?.children.orEmpty() else emptyList()
            } catch (e: Exception) { emptyList() }
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
                                binding.tvChildName.text = chosen.name
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
