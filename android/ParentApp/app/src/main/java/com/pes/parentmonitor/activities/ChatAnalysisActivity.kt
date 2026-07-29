package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.databinding.ActivityChatAnalysisBinding
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class ChatAnalysisActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityChatAnalysisBinding
    private lateinit var prefs: PrefsManager
    private var loadJob: Job? = null
    private var loadGeneration = 0
    private var displayedChildId = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityChatAnalysisBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Chat Analysis"

        binding.swipeRefresh.setOnRefreshListener { loadChatAnalysis() }
    }

    override fun onAuthenticatedResume() {
        loadChatAnalysis()
    }

    private fun loadChatAnalysis() {
        loadJob?.cancel()
        val generation = ++loadGeneration
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
        loadJob = lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(serverUrl)
                // Dedicated chat analytics from real captured messages + toxicity scores.
                val resp = api.getChatAnalysis(childId)
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val data = resp.body()!!
                    val total = data.stats?.totalMessages ?: 0
                    val avgTox = data.stats?.avgToxicity ?: 0.0
                    val tox = data.toxicityDistribution
                    val recent = data.recentMessages ?: emptyList()

                    if (total == 0) {
                        binding.tvChatRisk.text = "No chat captured yet"
                        binding.tvChatRisk.setTextColor(getColor(com.pes.parentmonitor.R.color.text_secondary))
                        binding.tvCommunicationPattern.text =
                            "Typed in-game messages and voice-to-text are analysed here for toxicity. " +
                            "Note: not every game has in-game text chat — voice-only or single-player " +
                            "games may produce no chat data, and that's expected."
                        binding.tvKeywordGuidance.text =
                            "Guidance is unavailable until typed chat or voice-to-text is captured. " +
                            "No chat data is not evidence that communication was safe or concerning."
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
                        sb.append("Recent messages: 🔴 ${tox.high} concerning · 🟡 ${tox.medium} borderline · 🟢 ${tox.safe} clean\n")
                    }
                    // Show how the recent sample splits between text the child actually
                    // typed in-game and speech that was transcribed to text, so the parent
                    // can tell real chat apart from voice-to-text.
                    val voiceCount = recent.count { isVoice(it.source) }
                    val typedCount = recent.size - voiceCount
                    sb.append("Channel mix: ⌨️ $typedCount typed · 🎙️ $voiceCount voice\n\n")

                    val flagged = recent.filter { (it.confidence ?: 0.0) > 0.3 }.take(5)
                    if (flagged.isNotEmpty()) {
                        sb.append("Flagged samples:\n")
                        flagged.forEach { m ->
                            val pct = "%.0f".format((m.confidence ?: 0.0) * 100)
                            val msg = (m.message ?: "").let { if (it.length > 50) it.take(47) + "…" else it }
                            // Tag each line with its origin: ⌨️ typed chat vs 🎙️ voice-to-text.
                            sb.append("• ${sourceLabel(m.source)} \"$msg\" ($pct%)\n")
                        }
                    } else {
                        sb.append("No concerning messages in the recent sample.")
                    }
                    binding.tvCommunicationPattern.text = sb.toString().trimEnd()

                    // Guidance keyed on the real toxicity level
                    binding.tvKeywordGuidance.text = buildKeywordGuidance(sev)
                } else {
                    showUnavailable()
                    Toast.makeText(
                        this@ChatAnalysisActivity,
                        "Chat analysis is unavailable (${resp.code()})",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                showUnavailable()
                Toast.makeText(this@ChatAnalysisActivity, "Load failed: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                if (generation == loadGeneration) {
                    binding.progressBar.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
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
        binding.tvChatRisk.text = "Unknown"
        binding.tvChatRisk.setTextColor(getColor(com.pes.parentmonitor.R.color.text_secondary))
        binding.tvCommunicationPattern.text =
            "Chat analysis is unavailable until data for the selected child loads."
        binding.tvKeywordGuidance.text =
            "No guidance is inferred while chat data is unavailable."
    }

    /** A line transcribed from the child's speech (Vosk STT) vs typed in-game text. */
    private fun isVoice(source: String?): Boolean = source?.lowercase() == "voice_stt"

    /** Short tag so the parent can tell typed chat apart from voice-to-text. */
    private fun sourceLabel(source: String?): String =
        if (isVoice(source)) "🎙️ Voice" else "⌨️ Typed"

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

        "at_risk" -> """
            🔍 Borderline Language to Watch:

            Some captured messages show elevated toxicity. Look for repeated insults,
            rage, bullying, or language that continues across several sessions.

            Helpful next steps:
            1. Ask calmly what happened in the game
            2. Discuss respectful communication and taking breaks
            3. Watch for repetition rather than judging one isolated message
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
