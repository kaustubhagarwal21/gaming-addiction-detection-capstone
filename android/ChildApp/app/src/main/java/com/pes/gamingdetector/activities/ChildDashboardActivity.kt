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
import com.pes.gamingdetector.api.TrendPoint
import com.pes.gamingdetector.databinding.ActivityChildDashboardBinding
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.launch

class ChildDashboardActivity : AppCompatActivity() {
    private lateinit var binding: ActivityChildDashboardBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
        loadDashboard()
    }

    private fun loadDashboard() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)

                // Load main dashboard and enriched data in parallel
                val dashResp    = api.getUserDashboard(prefs.userId)
                val enrichedResp = try { api.getChildEnriched(prefs.userId) } catch (_: Exception) { null }

                if (dashResp.isSuccessful && dashResp.body()?.success == true) {
                    val dash  = dashResp.body()!!
                    val stats = dash.stats

                    if (stats != null) {
                        binding.tvCurrentRisk.text    = stats.currentRisk.uppercase().replace("_", " ")
                        binding.tvRiskScore.text      = "${"%.0f".format(stats.riskScore * 100)}% risk score"
                        binding.tvTotalSessions.text  = "${stats.totalSessions}"
                        binding.tvTotalHours.text     = "${"%.1f".format(stats.totalHours)}h"
                        binding.tvAvgDaily.text       = "${"%.1f".format(stats.avgDailyHours)}h"
                        // Hero is on gradient — keep text white for legibility
                        binding.tvCurrentRisk.setTextColor(android.graphics.Color.WHITE)
                    }

                    dash.trendData?.let { setupTrendChart(it) }

                    val sessions = dash.recentSessions ?: emptyList()
                    binding.tvNoSessions.visibility = if (sessions.isEmpty()) View.VISIBLE else View.GONE
                    val sb = StringBuilder()
                    sessions.take(5).forEach { s ->
                        // risk_label is the internal key ("at_risk") — prettify for display
                        val nice = s.riskLabel.replace("_", " ")
                            .replaceFirstChar { it.uppercase() }
                        sb.append("• ${s.gameName} — $nice (${s.duration})\n")
                    }
                    binding.tvRecentSessions.text = sb.toString().trimEnd()
                }

                // Render enriched data (streak + limit)
                enrichedResp?.body()?.let { enriched ->
                    if (enriched.success) {
                        // Self-awareness message + streak card
                        enriched.selfAwarenessMessage?.let { msg ->
                            binding.tvSelfAwarenessMessage.text = msg
                        }
                        enriched.streak?.let { s ->
                            binding.cardStreak.visibility  = View.VISIBLE
                            binding.tvStreakCurrent.text   = "${s.currentStreak} days"
                            binding.tvStreakBest.text      = "${s.longestStreak} days"
                            // Badge = reward tier for the healthy-gaming streak (see the
                            // caption below). Locked until the first 3-day streak.
                            val badgeText = when {
                                s.currentStreak >= 30 -> "🥇 Gold"
                                s.currentStreak >= 14 -> "🥈 Silver"
                                s.currentStreak >= 7  -> "🥉 Bronze"
                                s.currentStreak >= 3  -> "⭐ Starter"
                                else                  -> "🔒"
                            }
                            binding.tvStreakBadge.text = badgeText
                        }

                        // Time limit card
                        enriched.limitStatus?.let { ls ->
                            binding.cardLimitStatus.visibility = View.VISIBLE
                            val pct    = ((ls.usedTodayHours / ls.dailyLimitHours) * 100).toInt().coerceIn(0, 100)
                            val status = if (ls.exceeded)
                                "LIMIT REACHED — used ${"%.1f".format(ls.usedTodayHours)}h of ${"%.1f".format(ls.dailyLimitHours)}h"
                            else
                                "Used ${"%.1f".format(ls.usedTodayHours)}h of ${"%.1f".format(ls.dailyLimitHours)}h — ${"%.1f".format(ls.remainingHours)}h remaining"
                            binding.tvLimitStatus.text           = status
                            binding.tvLimitStatus.setTextColor(
                                if (ls.exceeded) getColor(R.color.risk_high) else getColor(R.color.text_primary)
                            )
                            binding.limitProgressBar.progress    = pct
                        }
                    }
                }

            } catch (e: Exception) {
                val msg = if (e is java.io.IOException) "Cannot reach server — check Settings."
                          else "Load failed: ${e.message}"
                Toast.makeText(this@ChildDashboardActivity, msg, Toast.LENGTH_LONG).show()
            } finally {
                binding.progressBar.visibility    = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun setupTrendChart(trendData: List<TrendPoint>) {
        if (trendData.isEmpty()) return

        val entries = trendData.takeLast(14).mapIndexed { i, p ->
            Entry(i.toFloat(), (p.score * 100).toFloat())
        }
        val labels = trendData.takeLast(14).map { it.date.takeLast(5) }

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
            // Fixed 0–100% scale with the actual risk-band cutoffs drawn in, so the line
            // is read against "some concern" (33%) and "high concern" (67%).
            axisLeft.apply {
                axisMinimum = 0f
                axisMaximum = 100f
                granularity = 25f
                textColor = getColor(R.color.text_secondary)
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

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
