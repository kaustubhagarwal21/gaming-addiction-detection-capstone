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
                    val spoken = data.stats?.spokenMessages ?: 0
                    val avgTox = data.stats?.avgToxicity ?: 0.0
                    val tox = data.toxicityDistribution
                    val recent = data.recentMessages ?: emptyList()

                    // "Nothing captured" means NEITHER channel produced anything. Gating
                    // on typed chat alone blanked the whole screen for a child whose
                    // games have no text chat but who speaks throughout.
                    if (total == 0 && spoken == 0) {
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

                    // The server's average and distribution are TYPED-only (spoken lines
                    // are counted separately). Report each channel for what it is rather
                    // than presenting "0% over 0 messages" as a clean result while
                    // thousands of spoken lines sit unmentioned.
                    val sampleTox = recent.mapNotNull { it.confidence }
                    val shownAvg = if (total > 0) avgTox else sampleTox.average().takeIf {
                        sampleTox.isNotEmpty()
                    } ?: 0.0
                    binding.tvChatRisk.text = when {
                        total > 0 && spoken > 0 ->
                            "Avg toxicity: ${"%.0f".format(avgTox * 100)}%  ·  " +
                                "$total typed · $spoken spoken"
                        total > 0 -> "Avg toxicity: ${"%.0f".format(avgTox * 100)}%  ·  " +
                            "$total typed messages"
                        else -> "$spoken spoken lines analysed  ·  no typed chat in these games"
                    }
                    val sev = when {
                        shownAvg > 0.6 -> "addicted"
                        shownAvg > 0.3 -> "at_risk"
                        else           -> "casual"
                    }
                    binding.tvChatRisk.setTextColor(when (sev) {
                        "addicted" -> getColor(com.pes.parentmonitor.R.color.risk_high)
                        "at_risk"  -> getColor(com.pes.parentmonitor.R.color.risk_medium)
                        else       -> getColor(com.pes.parentmonitor.R.color.risk_low)
                    })

                    // Real toxicity distribution + a few recent samples
                    val sb = StringBuilder()
                    if (tox != null && total > 0) {
                        sb.append("Typed messages: 🔴 ${tox.high} concerning · 🟡 ${tox.medium} borderline · 🟢 ${tox.safe} clean\n")
                    } else if (spoken > 0) {
                        sb.append("No typed chat captured — the breakdown below is from " +
                            "transcribed speech.\n")
                    }
                    // Show how the recent sample splits between text the child actually
                    // typed in-game and speech that was transcribed to text, so the parent
                    // can tell real chat apart from voice-to-text.
                    val voiceCount = recent.count { isVoice(it.source) }
                    val typedCount = recent.size - voiceCount
                    val hindiCount = recent.count { langBadge(it.message) == "hi" }
                    sb.append("Channel mix: ⌨️ $typedCount typed · 🎙️ $voiceCount voice")
                    if (hindiCount > 0) sb.append(" · $hindiCount in Hindi script")
                    sb.append("\n\n")

                    val flagged = recent.filter { (it.confidence ?: 0.0) > 0.3 }.take(5)
                    if (flagged.isNotEmpty()) {
                        sb.append("Flagged samples:\n")
                        flagged.forEach { m ->
                            val pct = "%.0f".format((m.confidence ?: 0.0) * 100)
                            val msg = (m.message ?: "").let { if (it.length > 50) it.take(47) + "…" else it }
                            // Tag each line with its origin (⌨️ typed vs 🎙️ voice) and
                            // script-detected language, so the Hindi capability is visible.
                            sb.append("• ${sourceLabel(m.source)} · ${langBadge(m.message)} \"$msg\" ($pct%)\n")
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

    /** Script-based language tag: any Devanagari character marks the line "hi";
     *  everything else (incl. romanised Hinglish, which shares the Latin script
     *  with English) shows "en". Honest label for what is DETECTABLE client-side
     *  — the server-side model scores all three registers either way. */
    private fun langBadge(message: String?): String =
        if (message?.any { it in 'ऀ'..'ॿ' } == true) "hi" else "en"

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
