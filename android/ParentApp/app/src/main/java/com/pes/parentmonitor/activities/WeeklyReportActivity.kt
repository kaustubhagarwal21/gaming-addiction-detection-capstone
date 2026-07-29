package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.github.mikephil.charting.data.*
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.pes.parentmonitor.R
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.DailyHoursPoint
import com.pes.parentmonitor.api.ParentalDashboard
import com.pes.parentmonitor.api.TrendPoint
import com.pes.parentmonitor.databinding.ActivityWeeklyReportBinding
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.RiskPresentation
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class WeeklyReportActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityWeeklyReportBinding
    private lateinit var prefs: PrefsManager
    private var reportJob: Job? = null
    private var reportGeneration = 0
    private var displayedChildId = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityWeeklyReportBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Weekly Report"

        binding.swipeRefresh.setOnRefreshListener { loadReport() }
    }

    override fun onAuthenticatedResume() {
        loadReport()
    }

    private fun loadReport() {
        reportJob?.cancel()
        val generation = ++reportGeneration
        val childId = prefs.childUserId
        val serverUrl = prefs.serverUrl
        prepareForChild(childId)
        binding.progressBar.visibility = View.VISIBLE
        if (childId <= 0) {
            showUnavailable()
            binding.progressBar.visibility = View.GONE
            binding.swipeRefresh.isRefreshing = false
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        reportJob = lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(serverUrl)
                val resp = api.getParentalDashboard(childId)
                if (generation != reportGeneration || childId != prefs.childUserId) return@launch
                if (resp.isSuccessful && resp.body()?.success == true) {
                    render(resp.body()!!)
                } else {
                    showUnavailable()
                    Toast.makeText(
                        this@WeeklyReportActivity,
                        "Weekly report is unavailable (${resp.code()})",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation != reportGeneration || childId != prefs.childUserId) return@launch
                showUnavailable()
                val msg = if (e is java.io.IOException)
                    "Cannot reach server — check Settings."
                else "Load failed: ${e.message}"
                Toast.makeText(this@WeeklyReportActivity, msg, Toast.LENGTH_LONG).show()
            } finally {
                if (generation == reportGeneration) {
                    binding.progressBar.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
                    reportJob = null
                }
            }
        }
    }

    private fun prepareForChild(childId: Int) {
        if (displayedChildId == childId) return
        displayedChildId = childId
        supportActionBar?.subtitle = prefs.childName.takeIf { it.isNotBlank() }
        showUnavailable()
    }

    /** Neutral state for first load, sibling switches, and failed requests. */
    private fun showUnavailable() {
        binding.tvWeekHours.text = "—"
        binding.tvWeekSessions.text = "—"
        binding.tvAvgDaily.text = "—"
        binding.tvLateNight.text = "—"
        binding.tvRiskLevel.text = "Unknown"
        binding.tvRiskLevel.setTextColor(getColor(R.color.text_secondary))
        binding.riskBar.setBackgroundColor(getColor(R.color.text_secondary))
        binding.tvRiskContext.text = "Risk score unavailable"
        binding.tvTopGames.text = "Weekly game data unavailable"
        binding.tvActionItems.text =
            "• Report data is unavailable. Check the connection and refresh."
        setupBarChart(emptyList())
        setupChart(emptyList())
    }

    private fun render(dash: ParentalDashboard) {
        val weekHours = dash.totalHoursWeek
        // Average PER PLAY DAY (days that actually have gaming), not per calendar day —
        // avoids underestimating for a new account with <7 days of history. Other screens
        // (and the server's avg_daily) divide by 7; the layout caption says "hrs per play
        // day" so the two figures can coexist without looking contradictory.
        val daysWithData = dash.dailyHoursWeek?.count { it.hours > 0 }?.takeIf { it > 0 } ?: 7
        val avgDaily = weekHours?.div(daysWithData)
        val lateNight = dash.lateNightCount
        // Never substitute the all-time top-games count for a weekly metric.
        val sessionCount = dash.weekSessionCount

        binding.tvWeekHours.text = weekHours?.let { "%.1f".format(it) } ?: "—"
        binding.tvWeekSessions.text = sessionCount?.toString() ?: "—"
        binding.tvAvgDaily.text = avgDaily?.let { "%.1f".format(it) } ?: "—"
        binding.tvLateNight.text = lateNight?.toString() ?: "—"

        val risk = dash.currentRisk
        val score = dash.riskScore
        val color = when (risk?.lowercase()) {
            "addicted" -> getColor(R.color.risk_high)
            "at_risk"  -> getColor(R.color.risk_medium)
            "casual"   -> getColor(R.color.risk_low)
            else       -> getColor(R.color.text_secondary)
        }
        binding.tvRiskLevel.text = RiskPresentation.displayLabel(risk, dash.riskLabel)
        binding.tvRiskLevel.setTextColor(color)
        binding.riskBar.setBackgroundColor(color)
        binding.tvRiskContext.text = RiskPresentation.detailText(
            score,
            dash.riskPeriod?.label,
            dash.riskPeriod?.sessions
        )

        // Top games — this week's, not the all-time leaderboard (falls back for an
        // older backend that doesn't send the weekly list yet).
        val games = dash.topGamesWeek
        if (games == null) {
            binding.tvTopGames.text = "Weekly game breakdown unavailable"
        } else if (games.isEmpty()) {
            binding.tvTopGames.text = "No game data this week"
        } else {
            val sb = StringBuilder()
            games.take(5).forEachIndexed { i, g ->
                sb.append("${i + 1}. ${g.game} — ${"%.1f".format(g.hours)}h (${g.sessions} sessions)\n")
            }
            binding.tvTopGames.text = sb.toString().trimEnd()
        }

        // Daily bar chart
        setupBarChart(dash.dailyHoursWeek.orEmpty())

        // Trend chart
        setupChart(dash.trendData.orEmpty())

        // Action items based on risk
        binding.tvActionItems.text = buildActionItems(risk, weekHours ?: 0.0, lateNight ?: 0)
    }

    private fun setupBarChart(dailyHours: List<DailyHoursPoint>) {
        if (dailyHours.isEmpty()) {
            binding.barChart.clear()
            binding.barChart.invalidate()
            return
        }
        val entries = dailyHours.mapIndexed { i, d -> BarEntry(i.toFloat(), d.hours.toFloat()) }
        val labels  = dailyHours.map { it.day }

        val barColor = getColor(R.color.colorPrimary)
        val ds = BarDataSet(entries, "Hours").apply {
            color = barColor
            setDrawValues(true)
            valueTextSize = 9f
        }
        binding.barChart.apply {
            data = BarData(ds).also { it.barWidth = 0.6f }
            xAxis.valueFormatter = IndexAxisValueFormatter(labels)
            xAxis.granularity = 1f
            xAxis.setDrawGridLines(false)
            axisRight.isEnabled = false
            axisLeft.axisMinimum = 0f
            axisLeft.granularity = 1f
            legend.isEnabled = false
            description.isEnabled = false
            setFitBars(true)
            animateY(600)
            invalidate()
        }
    }

    private fun setupChart(trendData: List<TrendPoint>) {
        if (trendData.isEmpty()) {
            binding.lineChart.clear()
            binding.lineChart.invalidate()
            return
        }
        val pts = trendData.takeLast(14)
        val entries = pts.mapIndexed { i, p -> Entry(i.toFloat(), (p.score * 100).toFloat()) }
        val labels  = pts.map { it.date.takeLast(5) }

        val ds = LineDataSet(entries, "Risk (%)").apply {
            color = getColor(R.color.colorPrimary)
            setCircleColor(getColor(R.color.colorPrimary))
            lineWidth = 2.5f; circleRadius = 4f; setDrawValues(false)
            mode = LineDataSet.Mode.CUBIC_BEZIER
            fillColor = getColor(R.color.colorPrimary); setDrawFilled(true); fillAlpha = 30
        }
        binding.lineChart.apply {
            data = LineData(ds)
            xAxis.valueFormatter = IndexAxisValueFormatter(labels)
            xAxis.granularity = 1f; xAxis.labelRotationAngle = -30f
            axisRight.isEnabled = false
            axisLeft.axisMinimum = 0f; axisLeft.axisMaximum = 100f
            legend.isEnabled = false; description.isEnabled = false
            setTouchEnabled(true); animateX(800); invalidate()
        }
    }

    private fun buildActionItems(risk: String?, weekHours: Double, lateNight: Int): String {
        val items = mutableListOf<String>()

        when (risk?.lowercase()) {
            "addicted" -> {
                items += "Schedule an immediate family conversation about gaming habits"
                items += "Set a strict daily limit (recommended: max 1 hour)"
                items += "Consider consulting a counselor if patterns persist"
                items += "Remove devices from bedroom, especially after 9 PM"
                if (lateNight > 2) items += "Your child gamed late at night $lateNight times — address sleep schedule"
            }
            "at_risk" -> {
                items += "Have a calm discussion about healthy gaming boundaries"
                items += "Set clear gaming hours (e.g., only after homework)"
                if (weekHours > 20) items += "${String.format("%.0f", weekHours)}h this week is above healthy range (10-14h)"
                if (lateNight > 0) items += "$lateNight late-night sessions detected — consider parental controls for night hours"
                items += "Introduce at least one gaming-free day per week"
            }
            "casual" -> {
                items += "Gaming habits look healthy this week — keep it up!"
                if (weekHours > 14) items += "Hours are slightly elevated (${String.format("%.0f", weekHours)}h) — monitor trends"
                items += "Continue encouraging balance between gaming and other activities"
                items += "Praise your child for maintaining healthy habits"
            }
            else -> {
                items += "Risk information isn't available yet — complete a monitored gaming session and refresh"
            }
        }

        return items.joinToString("\n") { "• $it" }
    }

    override fun onSupportNavigateUp(): Boolean { finish(); return true }
}
