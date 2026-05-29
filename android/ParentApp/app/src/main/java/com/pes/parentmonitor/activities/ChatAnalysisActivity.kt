package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.databinding.ActivityChatAnalysisBinding
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.launch

class ChatAnalysisActivity : AppCompatActivity() {
    private lateinit var binding: ActivityChatAnalysisBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityChatAnalysisBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Chat Analysis"

        binding.swipeRefresh.setOnRefreshListener { loadChatAnalysis() }
        loadChatAnalysis()
    }

    private fun loadChatAnalysis() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                // Dedicated chat analytics from real captured messages + toxicity scores.
                val resp = api.getChatAnalysis(prefs.childUserId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val data = resp.body()!!
                    val total = data.stats?.totalMessages ?: 0
                    val avgTox = data.stats?.avgToxicity ?: 0.0
                    val tox = data.toxicityDistribution
                    val recent = data.recentMessages ?: emptyList()

                    if (total == 0) {
                        binding.tvChatRisk.text = "No chat captured yet"
                        binding.tvChatRisk.setTextColor(getColor(com.pes.parentmonitor.R.color.risk_low))
                        binding.tvCommunicationPattern.text =
                            "Captured in-game and voice-to-text messages will be analysed here for toxicity."
                        binding.tvKeywordGuidance.text = buildKeywordGuidance("casual")
                        return@launch
                    }

                    // Real average toxicity across captured messages
                    binding.tvChatRisk.text =
                        "Avg toxicity: ${"%.0f".format(avgTox * 100)}%  ·  $total messages analysed"
                    val sev = when {
                        avgTox > 0.6 -> "addicted"
                        avgTox > 0.3 -> "at_risk"
                        else         -> "casual"
                    }
                    binding.tvChatRisk.setTextColor(when (sev) {
                        "addicted" -> getColor(com.pes.parentmonitor.R.color.risk_high)
                        "at_risk"  -> getColor(com.pes.parentmonitor.R.color.risk_medium)
                        else       -> getColor(com.pes.parentmonitor.R.color.risk_low)
                    })

                    // Real toxicity distribution + a few recent samples
                    val sb = StringBuilder()
                    if (tox != null) {
                        sb.append("Recent messages: 🔴 ${tox.high} concerning · 🟡 ${tox.medium} borderline · 🟢 ${tox.safe} clean\n\n")
                    }
                    val flagged = recent.filter { (it.confidence ?: 0.0) > 0.3 }.take(5)
                    if (flagged.isNotEmpty()) {
                        sb.append("Flagged samples:\n")
                        flagged.forEach { m ->
                            val pct = "%.0f".format((m.confidence ?: 0.0) * 100)
                            val msg = (m.message ?: "").let { if (it.length > 50) it.take(47) + "…" else it }
                            sb.append("• \"$msg\" ($pct%)\n")
                        }
                    } else {
                        sb.append("No concerning messages in the recent sample.")
                    }
                    binding.tvCommunicationPattern.text = sb.toString().trimEnd()

                    // Guidance keyed on the real toxicity level
                    binding.tvKeywordGuidance.text = buildKeywordGuidance(sev)
                }
            } catch (e: Exception) {
                Toast.makeText(this@ChatAnalysisActivity, "Load failed: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                binding.progressBar.visibility = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun buildKeywordGuidance(risk: String): String = when (risk.lowercase()) {
        "addicted" -> """
            🔍 Keywords to Watch For:

            High-concern: "can't stop", "need to play", "just one more",
            "addicted", "obsessed", "hate everyone", extreme profanity

            What to do if you see these:
            1. Have a calm, non-judgmental conversation
            2. Ask about what's happening in the game
            3. Discuss how these feelings connect to real life
            4. Consider professional support if pattern persists
        """.trimIndent()

        else -> """
            🔍 Normal Gaming Language:

            Common gaming terms are not concerning: "gg", "rip", "clutch",
            "let's go", general competitive phrases

            Monitor for escalation to: constant rage expressions, addiction
            keywords, or bullying of other players.
        """.trimIndent()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
