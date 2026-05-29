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
import com.github.mikephil.charting.data.*
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
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
        loadDashboard()
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
        binding.tvCurrentRisk.text  = risk.uppercase().replace("_", " ")
        binding.tvRiskScore.text    = "${"%.0f".format(score * 100)}%"

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
        dash.topGames?.let  { setupTopGamesText(it) }

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

        // ── Explainable risk ───────────────────────────────────
        val factors = dash.riskExplanation ?: emptyList()
        if (factors.isNotEmpty()) {
            binding.cardRiskExplanation.visibility = View.VISIBLE
            val sb = StringBuilder()
            factors.forEachIndexed { i, f ->
                sb.append("${i + 1}. ${f.label}:  ${"%.1f".format(f.value)}  (${f.contributionPct.toInt()}% of risk)\n")
            }
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
            xAxis.valueFormatter     = IndexAxisValueFormatter(labels)
            xAxis.granularity        = 1f
            xAxis.labelRotationAngle = -30f
            axisRight.isEnabled      = false
            axisLeft.axisMinimum     = 0f
            axisLeft.axisMaximum     = 100f
            legend.isEnabled         = false
            description.isEnabled    = false
            setTouchEnabled(true)
            if (animate) animateX(800)
            invalidate()
        }
    }

    private fun setupTopGamesText(topGames: List<com.pes.parentmonitor.api.TopGame>) {
        if (topGames.isEmpty()) { binding.tvTopGames.text = "No game data yet"; return }
        val sb = StringBuilder()
        topGames.take(5).forEachIndexed { i, g ->
            sb.append("${i + 1}. ${g.game} — ${"%.1f".format(g.hours)} hrs (${g.sessions} sessions)\n")
        }
        binding.tvTopGames.text = sb.toString().trimEnd()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_parent, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_switch_child -> {
            prefs.childUserId = -1
            prefs.childName   = ""
            startActivity(Intent(this, LoginActivity::class.java))
            finishAffinity()
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
}
