package com.pes.parentmonitor.activities

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.R
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)

        val prefs = PrefsManager(this)
        lifecycleScope.launch {
            delay(1800)
            val intent = when {
                !prefs.isLoggedIn()       -> Intent(this@SplashActivity, LoginActivity::class.java)
                prefs.childUserId == -1   -> Intent(this@SplashActivity, LoginActivity::class.java)
                else                      -> Intent(this@SplashActivity, ParentalDashboardActivity::class.java)
            }
            startActivity(intent)
            finish()
        }
    }
}
