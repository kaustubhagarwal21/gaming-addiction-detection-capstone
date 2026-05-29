package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.databinding.ActivityRecommendationsBinding
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.launch

class RecommendationsActivity : AppCompatActivity() {
    private lateinit var binding: ActivityRecommendationsBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityRecommendationsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Recommendations"

        loadRecommendations()
    }

    private fun loadRecommendations() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getParentalDashboard(prefs.childUserId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val dash = resp.body()!!
                    val recs = dash.recommendations ?: emptyList()
                    val risk = dash.currentRisk ?: "casual"

                    binding.tvRiskContext.text = "Child's current risk: ${risk.uppercase()}"

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
                }
            } catch (e: Exception) {
                Toast.makeText(this@RecommendationsActivity, "Failed to load: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun buildGeneralTips(risk: String): String = when (risk.lowercase()) {
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

        else -> """
            ✅ Maintaining Healthy Habits:
            • Keep up the current balance — things look good!
            • Continue encouraging diverse activities
            • Maintain open conversations about gaming
            • Periodic check-ins to ensure continued balance
            • Praise responsible gaming behavior
        """.trimIndent()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
