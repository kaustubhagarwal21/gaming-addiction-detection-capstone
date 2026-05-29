package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.github.mikephil.charting.data.*
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.pes.parentmonitor.R
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.DailyHoursPoint
import com.pes.parentmonitor.api.ParentalDashboard
import com.pes.parentmonitor.api.TrendPoint
import com.pes.parentmonitor.databinding.ActivityWeeklyReportBinding
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.launch

class WeeklyReportActivity : AppCompatActivity() {
    private lateinit var binding: ActivityWeeklyReportBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityWeeklyReportBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Weekly Report"

        binding.swipeRefresh.setOnRefreshListener { loadReport() }
        loadReport()
    }

    private fun loadReport() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getParentalDashboard(prefs.childUserId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    render(resp.body()!!)
                }
            } catch (e: Exception) {
                val msg = if (e is java.io.IOException)
                    "Cannot reach server — check Settings."
                else "Load failed: ${e.message}"
                Toast.makeText(this@WeeklyReportActivity, msg, Toast.LENGTH_LONG).show()
            } finally {
                binding.progressBar.visibility = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun render(dash: ParentalDashboard) {
        val weekHours    = dash.totalHoursWeek ?: 0.0
        // Average only over days that actually have data (avoids underestimating
        // for a new account with fewer than 7 days of history).
        val daysWithData = dash.dailyHoursWeek?.count { it.hours > 0 }?.takeIf { it > 0 } ?: 7
        val avgDaily     = weekHours / daysWithData
        val lateNight    = dash.lateNightCount ?: 0
        // Real session count = sum of per-game session counts; trendData.size is
        // the number of trend points (≈ days), not sessions.
        val sessionCount = dash.topGames?.sumOf { it.sessions } ?: 0

        binding.tvWeekHours.text    = "%.1f".format(weekHours)
        binding.tvWeekSessions.text = sessionCount.toString()
        binding.tvAvgDaily.text     = "%.1f".format(avgDaily)
        binding.tvLateNight.text    = lateNight.toString()

        val risk = dash.currentRisk ?: "casual"
        val score = dash.riskScore ?: 0.0
        val color = when (risk.lowercase()) {
            "addicted" -> getColor(R.color.risk_high)
            "at_risk"  -> getColor(R.color.risk_medium)
            else       -> getColor(R.color.risk_low)
        }
        binding.tvRiskLevel.text = risk.uppercase().replace("_", "-")
        binding.tvRiskLevel.setTextColor(color)
        binding.riskBar.setBackgroundColor(color)
        binding.tvRiskContext.text = "${"%.0f".format(score * 100)}% risk score"

        // Top games
        val games = dash.topGames
        if (games.isNullOrEmpty()) {
            binding.tvTopGames.text = "No game data this week"
        } else {
            val sb = StringBuilder()
            games.take(5).forEachIndexed { i, g ->
                sb.append("${i + 1}. ${g.game} — ${"%.1f".format(g.hours)}h (${g.sessions} sessions)\n")
            }
            binding.tvTopGames.text = sb.toString().trimEnd()
        }

        // Daily bar chart
        dash.dailyHoursWeek?.let { setupBarChart(it) }

        // Trend chart
        dash.trendData?.let { setupChart(it) }

        // Action items based on risk
        binding.tvActionItems.text = buildActionItems(risk, weekHours, lateNight)
    }

    private fun setupBarChart(dailyHours: List<DailyHoursPoint>) {
        if (dailyHours.isEmpty()) return
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
        if (trendData.isEmpty()) return
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

    private fun buildActionItems(risk: String, weekHours: Double, lateNight: Int): String {
        val items = mutableListOf<String>()

        when (risk.lowercase()) {
            "addicted" -> {
                items += "Schedule an immediate family conversation about gaming habits"
                items += "Set a strict daily limit (recommended: max 2 hours)"
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
            else -> {
                items += "Gaming habits look healthy this week — keep it up!"
                if (weekHours > 14) items += "Hours are slightly elevated (${String.format("%.0f", weekHours)}h) — monitor trends"
                items += "Continue encouraging balance between gaming and other activities"
                items += "Praise your child for maintaining healthy habits"
            }
        }

        return items.joinToString("\n") { "• $it" }
    }

    override fun onSupportNavigateUp(): Boolean { finish(); return true }
}
