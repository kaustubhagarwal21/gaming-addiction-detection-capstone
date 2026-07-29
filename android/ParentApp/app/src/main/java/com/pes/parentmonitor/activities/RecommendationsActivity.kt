package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.databinding.ActivityRecommendationsBinding
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.RiskPresentation
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class RecommendationsActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityRecommendationsBinding
    private lateinit var prefs: PrefsManager
    private var loadJob: Job? = null
    private var loadGeneration = 0
    private var displayedChildId = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityRecommendationsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Recommendations"
    }

    override fun onAuthenticatedResume() {
        loadRecommendations()
    }

    private fun loadRecommendations() {
        loadJob?.cancel()
        val generation = ++loadGeneration
        val childId = prefs.childUserId
        val serverUrl = prefs.serverUrl
        prepareForChild(childId)
        binding.progressBar.visibility = View.VISIBLE
        if (childId <= 0) {
            showUnavailable()
            binding.progressBar.visibility = View.GONE
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        loadJob = lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(serverUrl)
                val resp = api.getParentalDashboard(childId)
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val dash = resp.body()!!
                    val recs = dash.recommendations ?: emptyList()
                    val risk = dash.currentRisk

                    val label = RiskPresentation.displayLabel(risk, dash.riskLabel)
                    val details = RiskPresentation.detailText(
                        dash.riskScore,
                        dash.riskPeriod?.label,
                        dash.riskPeriod?.sessions
                    )
                    binding.tvRiskContext.text =
                        "Child's latest daily risk: $label\n$details"

                    if (recs.isEmpty()) {
                        binding.tvNoRecs.visibility = View.VISIBLE
                        binding.tvRecommendations.visibility = View.GONE
                    } else {
                        binding.tvNoRecs.visibility = View.GONE
                        binding.tvRecommendations.visibility = View.VISIBLE
                        val sb = StringBuilder()
                        recs.forEachIndexed { i, rec ->
                            sb.append("${i + 1}. $rec\n\n")
                        }
                        binding.tvRecommendations.text = sb.toString().trimEnd()
                    }

                    binding.tvGeneralTips.text = buildGeneralTips(risk)
                } else {
                    showUnavailable()
                    Toast.makeText(
                        this@RecommendationsActivity,
                        "Recommendations are unavailable (${resp.code()})",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                showUnavailable()
                Toast.makeText(this@RecommendationsActivity, "Failed to load: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                if (generation == loadGeneration) {
                    binding.progressBar.visibility = View.GONE
                    loadJob = null
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

    private fun showUnavailable() {
        binding.tvRiskContext.text = "Child's latest daily risk: Unknown\nRisk score unavailable"
        binding.tvNoRecs.text = "Recommendations unavailable until risk data loads"
        binding.tvNoRecs.visibility = View.VISIBLE
        binding.tvRecommendations.text = ""
        binding.tvRecommendations.visibility = View.GONE
        binding.tvGeneralTips.text =
            "General guidance is unavailable until the selected child's data loads."
    }

    private fun buildGeneralTips(risk: String?): String = when (risk?.lowercase()) {
        "addicted" -> """
            ⚠️ Immediate Actions Recommended:
            • Set strict daily time limits (max 1 hour/day)
            • Remove gaming devices from bedroom
            • Schedule regular offline activities
            • Consider consulting a counselor or therapist
            • Use parental control apps to enforce time limits
            • Establish a family technology agreement
        """.trimIndent()

        "at_risk" -> """
            📋 Preventive Measures:
            • Discuss healthy gaming habits with your child
            • Set agreed gaming time limits (1-2 hours/day)
            • Ensure gaming doesn't interfere with sleep, study, meals
            • Encourage physical activities and social hobbies
            • Monitor late-night sessions closely
            • Check in regularly about how gaming makes them feel
        """.trimIndent()

        "casual" -> """
            ✅ Maintaining Healthy Habits:
            • Keep up the current balance — things look good!
            • Continue encouraging diverse activities
            • Maintain open conversations about gaming
            • Periodic check-ins to ensure continued balance
            • Praise responsible gaming behavior
        """.trimIndent()

        else -> """
            Risk information isn't available yet.
            Complete a gaming session while monitoring is active, then check again.
        """.trimIndent()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
