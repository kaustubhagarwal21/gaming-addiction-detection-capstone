package com.pes.gamingdetector.activities

import android.os.Bundle
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import java.time.LocalDate
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivityReflectionBinding
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.launch

class ReflectionActivity : AppCompatActivity() {

    private lateinit var binding: ActivityReflectionBinding
    private lateinit var prefs: PrefsManager
    private var selectedMood: Int = 3

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityReflectionBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Check-in"

        // A prompt that changes daily so the check-in never feels like the same form twice.
        val prompts = listOf(
            "How did today feel? Tap the face that fits 👇",
            "What's your vibe right now?",
            "Real quick — how are you doing today?",
            "Check in with yourself — how's your mood?",
            "One tap: how was your day?",
            "How's your energy after today?",
            "Be honest — how are you feeling today?"
        )
        binding.tvPrompt.text = prompts[LocalDate.now().dayOfYear % prompts.size]
        showCheckinStreak()

        val moodViews = listOf(binding.mood1, binding.mood2, binding.mood3, binding.mood4, binding.mood5)
        moodViews.forEach { view ->
            view.setOnClickListener {
                selectedMood = (view.tag as String).toInt()
                moodViews.forEach { it.alpha = 0.3f }
                view.alpha = 1.0f
                view.scaleX = 1.15f
                view.scaleY = 1.15f
            }
        }
        // Default selection: mood 3
        binding.mood3.alpha = 1.0f
        listOf(binding.mood1, binding.mood2, binding.mood4, binding.mood5).forEach { it.alpha = 0.5f }

        binding.btnSubmit.setOnClickListener { submit() }
    }

    private fun submit() {
        val sleep = binding.sliderSleep.value.toInt()
        val energy = binding.sliderEnergy.value.toInt()
        val note = binding.etNote.text?.toString()?.trim() ?: ""

        binding.btnSubmit.isEnabled = false
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val body = mutableMapOf<String, Any>(
                    "user_id" to prefs.userId,
                    "mood_rating" to selectedMood,
                    "sleep_quality" to sleep,
                    "energy_level" to energy
                )
                if (note.isNotEmpty()) body["note"] = note
                val resp = api.postReflection(body)
                if (resp.isSuccessful) {
                    celebrateAndFinish()
                } else {
                    Toast.makeText(this@ReflectionActivity, "Couldn't save — try again", Toast.LENGTH_SHORT).show()
                    binding.btnSubmit.isEnabled = true
                }
            } catch (e: Exception) {
                Toast.makeText(this@ReflectionActivity, "Network error", Toast.LENGTH_SHORT).show()
                binding.btnSubmit.isEnabled = true
            }
        }
    }

    /** Show the live check-in streak (hidden once it lapses, so it never shows stale). */
    private fun showCheckinStreak() {
        val s     = prefs.checkinStreak
        val today = LocalDate.now().toString()
        val yest  = LocalDate.now().minusDays(1).toString()
        val alive = prefs.lastCheckinDate == today || prefs.lastCheckinDate == yest
        if (s > 0 && alive) {
            binding.tvCheckinStreak.text = "🔥 $s-day check-in streak"
            binding.tvCheckinStreak.visibility = View.VISIBLE
        } else {
            binding.tvCheckinStreak.visibility = View.GONE
        }
    }

    /** Reward the child for checking in: grow the streak and celebrate, so it feels worth
     *  doing rather than a chore they'd skip. Streak counts once per day. */
    private fun celebrateAndFinish() {
        val today = LocalDate.now().toString()
        val yest  = LocalDate.now().minusDays(1).toString()
        val newStreak = when (prefs.lastCheckinDate) {
            today -> prefs.checkinStreak.coerceAtLeast(1)   // already counted today
            yest  -> prefs.checkinStreak + 1                // consecutive day
            else  -> 1                                      // fresh start
        }
        prefs.checkinStreak   = newStreak
        prefs.lastCheckinDate = today

        val rewards = listOf(
            "Nice — that's real self-awareness 💪",
            "Thanks for being honest 💚",
            "Checking in keeps you balanced 🌟",
            "Future you says thanks 🙌",
            "Small habit, big difference ✨"
        )
        val headline = if (newStreak >= 2) "🔥 $newStreak-day streak!" else "✅ Checked in!"
        AlertDialog.Builder(this)
            .setTitle("Done! 🎉")
            .setMessage("$headline\n\n${rewards.random()}")
            .setPositiveButton("Yay", null)
            .setOnDismissListener { finish() }
            .show()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
