package com.pes.gamingdetector.activities

import android.os.Bundle
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
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
                    Toast.makeText(this@ReflectionActivity, "Thanks for checking in 💚", Toast.LENGTH_SHORT).show()
                    finish()
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

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
