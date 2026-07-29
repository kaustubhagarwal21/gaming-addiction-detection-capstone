package com.pes.gamingdetector.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.github.mikephil.charting.components.LimitLine
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.data.*
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.github.mikephil.charting.formatter.ValueFormatter
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.ChildEnrichedResponse
import com.pes.gamingdetector.api.DashboardStats
import com.pes.gamingdetector.api.RiskThresholds
import com.pes.gamingdetector.api.SessionSummary
import com.pes.gamingdetector.api.TrendPoint
import com.pes.gamingdetector.databinding.ActivityChildDashboardBinding
import com.pes.gamingdetector.util.ChildDashboardUiLogic
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.RiskPresentation
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class ChildDashboardActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityChildDashboardBinding
    private lateinit var prefs: PrefsManager
    private var loadJob: Job? = null
    private var loadGeneration = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!ensureAuthenticatedOnCreate()) return
        binding = ActivityChildDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "My Dashboard"

        binding.swipeRefresh.setOnRefreshListener { loadDashboard() }
        binding.btnViewAllSessions.setOnClickListener {
            startActivity(Intent(this, SessionHistoryActivity::class.java))
        }
        binding.cardCounselor.setOnClickListener {
            startActivity(Intent(this, CounselorActivity::class.java))
        }
        binding.cardReflection.setOnClickListener {
            startActivity(Intent(this, ReflectionActivity::class.java))
        }
    }

    override fun onAuthenticatedResume() {
        // Load on first display and refresh after returning from another screen.
        loadDashboard()
    }

    private fun loadDashboard() {
        if (loadJob?.isActive == true) return
        val generation = ++loadGeneration
        binding.progressBar.visibility = View.VISIBLE
        loadJob = lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)

                // Load main dashboard and enriched data in parallel
                val dashResp    = api.getUserDashboard(prefs.userId)
                val enrichedResp = try {
                    api.getChildEnriched(prefs.userId)
                } catch (e: CancellationException) {
                    throw e
                } catch (_: Exception) {
                    null
                }

                if (generation == loadGeneration &&
                    dashResp.isSuccessful && dashResp.body()?.success == true
                ) {
                    val dash  = dashResp.body()!!
                    renderStats(dash.stats)
                    setupTrendChart(dash.trendData.orEmpty(), dash.riskThresholds)
                    renderRecentSessions(dash.recentSessions.orEmpty())
                }

                // A missing/failed enriched response is a complete optional-state update,
                // not permission to leave a previous streak or limit visible.
                val enriched = enrichedResp
                    ?.takeIf { it.isSuccessful }
                    ?.body()
                if (generation == loadGeneration) renderEnriched(enriched)

            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation == loadGeneration) {
                    val msg = if (e is java.io.IOException)
                        "Cannot reach server — check Settings."
                    else
                        "Load failed: ${e.message}"
                    Toast.makeText(this@ChildDashboardActivity, msg, Toast.LENGTH_LONG).show()
                }
            } finally {
                if (generation == loadGeneration) {
                    binding.progressBar.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
                    loadJob = null
                }
            }
        }
    }

    override fun onStop() {
        ++loadGeneration
        loadJob?.cancel()
        loadJob = null
        if (::binding.isInitialized) {
            binding.progressBar.visibility = View.GONE
            binding.swipeRefresh.isRefreshing = false
        }
        super.onStop()
    }

    private fun renderStats(stats: DashboardStats?) {
        if (stats == null) {
            binding.tvCurrentRisk.text = "\u2014"
            binding.tvRiskScore.text = "\u2014"
            binding.tvRiskPeriod.text = ""
            binding.tvRiskPeriod.visibility = View.GONE
            binding.tvTotalSessions.text = "\u2014"
            binding.tvTotalHours.text = "\u2014"
            binding.tvAvgDaily.text = "\u2014"
            return
        }

        binding.tvCurrentRisk.text = RiskPresentation.displayLabel(
            stats.currentRisk,
            stats.riskLabel
        )
        binding.tvRiskScore.text = RiskPresentation.riskScoreText(stats.riskScore)
        val periodText = RiskPresentation.periodText(
            stats.riskPeriod?.label,
            stats.riskPeriod?.sessions
        )
        binding.tvRiskPeriod.text = periodText.orEmpty()
        binding.tvRiskPeriod.visibility = if (periodText == null) View.GONE else View.VISIBLE
        binding.tvTotalSessions.text = "${stats.totalSessions}"
        binding.tvTotalHours.text = "${"%.1f".format(stats.totalHours)}h"
        binding.tvAvgDaily.text = "${"%.1f".format(stats.avgDailyHours)}h"
        // Hero is on gradient — keep text white for legibility.
        binding.tvCurrentRisk.setTextColor(android.graphics.Color.WHITE)
    }

    private fun renderRecentSessions(sessions: List<SessionSummary>) {
        val empty = sessions.isEmpty()
        binding.tvNoSessions.visibility = if (empty) View.VISIBLE else View.GONE
        binding.tvRecentSessions.visibility = if (empty) View.GONE else View.VISIBLE
        val sb = StringBuilder()
        sessions.take(5).forEach { session ->
            // These rows intentionally remain per-session; only their family-facing
            // terminology is shared with the daily headline.
            val nice = RiskPresentation.displayLabel(session.riskLabel)
            sb.append("• ${session.gameName} — $nice (${session.duration})\n")
        }
        // Always assign, including the empty case, so an earlier response cannot linger.
        binding.tvRecentSessions.text = sb.toString().trimEnd()
    }

    private fun renderEnriched(enriched: ChildEnrichedResponse?) {
        val state = ChildDashboardUiLogic.optionalState(enriched)

        binding.cardStreak.visibility = if (state.showStreak) View.VISIBLE else View.GONE
        binding.tvSelfAwarenessMessage.text = state.selfAwarenessMessage
        binding.tvStreakCurrent.text = "${state.currentStreakDays} days"
        binding.tvStreakBest.text = "${state.longestStreakDays} days"
        binding.tvStreakBadge.text = state.streakBadge

        binding.cardLimitStatus.visibility = if (state.showLimit) View.VISIBLE else View.GONE
        val status = if (!state.showLimit) {
            ""
        } else if (state.limitExceeded) {
            "LIMIT REACHED — used ${"%.1f".format(state.usedTodayHours)}h of " +
                "${"%.1f".format(state.dailyLimitHours)}h"
        } else {
            "Used ${"%.1f".format(state.usedTodayHours)}h of " +
                "${"%.1f".format(state.dailyLimitHours)}h — " +
                "${"%.1f".format(state.remainingHours)}h remaining"
        }
        binding.tvLimitStatus.text = status
        binding.tvLimitStatus.setTextColor(
            if (state.limitExceeded) getColor(R.color.risk_high)
            else getColor(R.color.text_primary)
        )
        binding.limitProgressBar.progress = state.limitProgress
    }

    private fun setupTrendChart(
        trendData: List<TrendPoint>,
        thresholds: RiskThresholds?,
    ) {
        val recentPoints = trendData.takeLast(14).filter { it.score.isFinite() }
        if (recentPoints.isEmpty()) {
            clearTrendChart()
            return
        }

        val configured = thresholds?.let { t ->
            val some = t.someConcern
            val high = t.highConcern
            if (some != null && high != null && some.isFinite() && high.isFinite() &&
                some in 0.0..1.0 && high in 0.0..1.0 && some < high) {
                some to high
            } else null
        }
        val (someConcern, highConcern) = configured ?: (0.33 to 0.67)

        val entries = recentPoints.mapIndexed { i, p ->
            Entry(i.toFloat(), (p.score.coerceIn(0.0, 1.0) * 100).toFloat())
        }
        val labels = recentPoints.map { it.date.takeLast(5) }

        val dataSet = LineDataSet(entries, "Daily risk %").apply {
            color = getColor(R.color.colorPrimary)
            setCircleColor(getColor(R.color.colorPrimary))
            lineWidth = 2f
            circleRadius = 4f
            setDrawValues(false)
            mode = LineDataSet.Mode.CUBIC_BEZIER
            setDrawFilled(true)
            fillColor = getColor(R.color.colorPrimary)
            fillAlpha = 28
        }

        binding.lineChart.apply {
            data = LineData(dataSet)
            xAxis.apply {
                valueFormatter = IndexAxisValueFormatter(labels)
                granularity = 1f
                position = XAxis.XAxisPosition.BOTTOM
                setDrawGridLines(false)
                textColor = getColor(R.color.text_primary)   // dark = clearly visible
                textSize = 10f
                labelRotationAngle = -45f
                setAvoidFirstLastClipping(true)
            }
            extraBottomOffset = 18f   // room for the rotated date labels (was clipped)
            // Fixed 0–100% scale with the backend's active risk-band cutoffs. Old
            // servers omit them, so retain the historical 33% / 67% fallback.
            axisLeft.apply {
                axisMinimum = 0f
                axisMaximum = 100f
                granularity = 25f
                textColor = getColor(R.color.text_secondary)
                valueFormatter = object : ValueFormatter() {
                    override fun getFormattedValue(value: Float) = "${value.toInt()}%"
                }
                removeAllLimitLines()
                addLimitLine(LimitLine((someConcern * 100).toFloat(), "Some concern").apply {
                    lineColor = getColor(R.color.risk_medium); lineWidth = 1.2f
                    textColor = getColor(R.color.risk_medium); textSize = 9f
                })
                addLimitLine(LimitLine((highConcern * 100).toFloat(), "High concern").apply {
                    lineColor = getColor(R.color.risk_high); lineWidth = 1.2f
                    textColor = getColor(R.color.risk_high); textSize = 9f
                })
            }
            axisRight.isEnabled = false
            legend.isEnabled = false
            description.isEnabled = false
            setTouchEnabled(true)
            isDragEnabled = true
            setScaleEnabled(false)
            animateX(800)
            invalidate()
        }
    }

    private fun clearTrendChart() {
        binding.lineChart.apply {
            clear()
            xAxis.valueFormatter = IndexAxisValueFormatter(emptyList())
            axisLeft.removeAllLimitLines()
            invalidate()
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
