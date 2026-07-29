package com.pes.gamingdetector.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.BuildConfig
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.LoginRequest
import com.pes.gamingdetector.databinding.ActivityLoginBinding
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {
    private lateinit var binding: ActivityLoginBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        binding.btnLogin.setOnClickListener { doLogin() }
        binding.tvCreateAccount.setOnClickListener {
            startActivity(Intent(this, RegisterActivity::class.java))
        }
        // Backend switching is a developer/setup tool, not a way around the parent-PIN
        // gate on family/game settings. Production uses the fixed HTTPS backend.
        binding.tvSettings.visibility = if (BuildConfig.DEBUG) View.VISIBLE else View.GONE
        binding.tvSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java).apply {
                putExtra(SettingsActivity.EXTRA_SERVER_SETUP_ONLY, true)
            })
        }
    }

    private fun doLogin() {
        val pin = binding.etPin.text.toString().trim()
        if (pin.isEmpty()) {
            binding.etPin.error = "Enter your PIN"
            return
        }

        binding.btnLogin.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.login(LoginRequest(pin = pin, role = "child"))
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val body = resp.body()!!
                    prefs.authToken = body.token   // set first so following calls are authenticated
                    prefs.userId = body.userId
                    prefs.userName = body.name
                    body.familyCode?.let { prefs.familyCode = it }   // shown later in Settings
                    startActivity(Intent(this@LoginActivity, HomeActivity::class.java))
                    finish()
                } else {
                    Toast.makeText(this@LoginActivity, "Invalid PIN", Toast.LENGTH_SHORT).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@LoginActivity, "Cannot reach server: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                if (isActive && !isFinishing && !isDestroyed) {
                    binding.btnLogin.isEnabled = true
                    binding.progressBar.visibility = View.GONE
                }
            }
        }
    }
}
