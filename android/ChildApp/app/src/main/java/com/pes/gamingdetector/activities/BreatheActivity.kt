package com.pes.gamingdetector.activities

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.databinding.ActivityBreatheBinding
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * A simple guided box-breathing reset — a healthy, screen-calming alternative to
 * "just one more game". The circle grows on the inhale and shrinks on the exhale;
 * the child follows along. Purely on-device, no data collected.
 */
class BreatheActivity : AppCompatActivity() {
    private lateinit var binding: ActivityBreatheBinding

    private val inhaleMs = 4000L
    private val holdMs   = 2000L
    private val exhaleMs = 4000L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityBreatheBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.breathingCircle.scaleX = 0.55f
        binding.breathingCircle.scaleY = 0.55f
        binding.btnDone.setOnClickListener { finish() }

        startBreathing()
    }

    private fun startBreathing() {
        lifecycleScope.launch {
            // Tiny settle before the first inhale.
            delay(600)
            while (isActive) {
                binding.tvPhase.text = "Breathe in…"
                binding.breathingCircle.animate().scaleX(1f).scaleY(1f)
                    .setDuration(inhaleMs).start()
                delay(inhaleMs)

                binding.tvPhase.text = "Hold"
                delay(holdMs)

                binding.tvPhase.text = "Breathe out…"
                binding.breathingCircle.animate().scaleX(0.55f).scaleY(0.55f)
                    .setDuration(exhaleMs).start()
                delay(exhaleMs)
            }
        }
    }
}
