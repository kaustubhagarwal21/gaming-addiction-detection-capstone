package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.databinding.ActivityEmotionInsightsBinding
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import org.json.JSONObject

class EmotionInsightsActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityEmotionInsightsBinding
    private lateinit var prefs: PrefsManager
    private var loadJob: Job? = null
    private var loadGeneration = 0
    private var displayedChildId = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityEmotionInsightsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Emotion Insights"

        binding.swipeRefresh.setOnRefreshListener { loadEmotions() }
    }

    override fun onAuthenticatedResume() {
        loadEmotions()
    }

    private fun loadEmotions() {
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
                val api  = ApiClient.getInstance(serverUrl)
                // Dedicated emotion analytics from real voice-event data.
                val resp = api.getEmotions(childId)
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val data = resp.body()!!
                    val dist = data.emotionDistribution ?: emptyList()
                    val recent = data.recentSessions ?: emptyList()

                    val totalSamples = dist.sumOf { it.n }
                    if (dist.isEmpty() || totalSamples <= 0) {
                        binding.tvRiskContext.text = "No voice data yet"
                        binding.tvEmotionByGame.text =
                            "Voice emotion analysis appears here once your child plays with voice monitoring on " +
                            "and actually speaks during gameplay. Silent or single-player sessions produce no " +
                            "voice data, and that's expected."
                        binding.tvEmotionTrend.text = ""
                        binding.tvEmotionAdvice.text = "Voice emotion guidance is unavailable until speech is captured. " +
                            "No voice data does not mean the session was emotionally healthy or unhealthy."
                        return@launch
                    }

                    // Dominant emotion overall (most frequent)
                    val dominant = dist.maxByOrNull { it.n }?.emotion ?: "neutral"
                    binding.tvRiskContext.text =
                        "Dominant emotion: ${dominant.replaceFirstChar { it.uppercase() }}  ($totalSamples voice samples)"

                    // Emotion distribution (real counts + avg intensity)
                    val sb = StringBuilder("Emotion breakdown:\n")
                    dist.forEach { e ->
                        val emoji = emojiFor(e.emotion)
                        val pct = if (totalSamples > 0) e.n * 100 / totalSamples else 0
                        val inten = e.avgIntensity?.let { " · avg intensity ${"%.0f".format(it * 100)}%" } ?: ""
                        sb.append("$emoji ${(e.emotion ?: "?").replaceFirstChar { it.uppercase() }}: $pct% (${e.n})$inten\n")
                    }
                    binding.tvEmotionByGame.text = sb.toString().trimEnd()

                    // Dominant emotion per recent session
                    if (recent.isNotEmpty()) {
                        val rb = StringBuilder("Recent sessions:\n")
                        recent.take(7).forEach { r ->
                            val emoji = emojiFor(r.dominantEmotion)
                            val date = r.startTime?.take(10) ?: ""
                            rb.append("$emoji ${r.gameName ?: "Game"} ($date): ${r.dominantEmotion ?: "—"}\n")
                        }
                        binding.tvEmotionTrend.text = rb.toString().trimEnd()
                    } else {
                        binding.tvEmotionTrend.text = ""
                    }

                    // Advice keyed on the dominant emotion (real signal, not risk template)
                    val pseudoRisk = when (dominant.lowercase()) {
                        "angry"      -> "addicted"
                        "frustrated" -> "at_risk"
                        else         -> "casual"
                    }
                    binding.tvEmotionAdvice.text = buildEmotionAdvice(pseudoRisk)
                } else {
                    showUnavailable()
                    Toast.makeText(
                        this@EmotionInsightsActivity,
                        "Emotion insights are unavailable (${resp.code()})",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                showUnavailable()
                Toast.makeText(this@EmotionInsightsActivity, "Load failed: ${e.message}", Toast.LENGTH_SHORT).show()
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
        binding.tvRiskContext.text = "Voice emotion data unavailable"
        binding.tvEmotionByGame.text =
            "Emotion insights are unavailable until data for the selected child loads."
        binding.tvEmotionTrend.text = ""
        binding.tvEmotionAdvice.text =
            "No emotional-state guidance is inferred while voice data is unavailable."
    }

    private fun emojiFor(emotion: String?): String = when (emotion?.lowercase()) {
        "angry"      -> "😡"
        "frustrated" -> "😟"
        "excited"    -> "🤩"
        "neutral"    -> "😊"
        else         -> "🎮"
    }

    private fun buildEmotionAdvice(risk: String): String = when (risk.lowercase()) {
        "addicted" -> """
            🔴 Stress Indicators HIGH

            Detected patterns suggest your child is experiencing:
            • Frustration and anger during gameplay
            • Emotional dysregulation after losing
            • Difficulty transitioning away from gaming

            Suggested Actions:
            • Schedule gaming-free relaxation activities
            • Practice deep breathing or mindfulness together
            • Set clear "cool-down" rules after intense sessions
            • Discuss healthy coping mechanisms for in-game frustration
        """.trimIndent()

        "at_risk" -> """
            🟡 Moderate Stress Indicators

            Your child may be experiencing:
            • Occasional frustration during competitive games
            • Mild emotional reactions to in-game events

            Suggested Actions:
            • Encourage regular breaks every 45-60 minutes
            • Introduce stress management activities
            • Discuss how in-game events affect real emotions
            • Praise calm, sportsmanlike behavior
        """.trimIndent()

        else -> """
            🟢 Emotional State Looks Healthy

            Your child appears to be:
            • Gaming with a balanced emotional state
            • Handling wins and losses appropriately

            Keep It Up:
            • Continue reinforcing positive gaming habits
            • Celebrate good sportsmanship
            • Maintain open conversations about gaming experiences
        """.trimIndent()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
