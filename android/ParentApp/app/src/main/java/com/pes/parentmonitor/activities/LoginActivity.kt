package com.pes.parentmonitor.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.firebase.messaging.FirebaseMessaging
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.LoginRequest
import com.pes.parentmonitor.databinding.ActivityLoginBinding
import com.pes.parentmonitor.util.PrefsManager
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
        binding.tvSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
    }

    private fun registerFcmToken(prefs: PrefsManager) {
        try {
            FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
                if (token.isNullOrEmpty()) return@addOnSuccessListener
                prefs.fcmToken = token
                lifecycleScope.launch {
                    try {
                        val api  = ApiClient.getInstance(prefs.serverUrl)
                        val body = mapOf<String, Any>("user_id" to prefs.parentId, "fcm_token" to token)
                        api.updateFcmToken(body)
                    } catch (_: Exception) {}
                }
            }
        } catch (_: Exception) {
            // Firebase not configured — FCM push disabled, polling still works
        }
    }

    private fun doLogin() {
        val pin = binding.etPin.text.toString().trim()
        if (pin.isEmpty()) {
            binding.etPin.error = "Enter your PIN"
            return
        }
        val familyCode = binding.etFamilyCode.text.toString().trim().uppercase()

        binding.btnLogin.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.login(
                    LoginRequest(pin = pin, role = "parent", familyCode = familyCode.ifBlank { null }))
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val body = resp.body()!!
                    prefs.authToken = body.token   // set first so following calls are authenticated
                    prefs.parentId = body.userId
                    prefs.parentName = body.name
                    registerFcmToken(prefs)

                    val children = body.children
                    if (!children.isNullOrEmpty()) {
                        val parcels = ArrayList(children.map {
                            ChildSelectActivity.ChildInfoParcel(it.userId, it.name, it.age ?: 0)
                        })
                        if (parcels.size == 1) {
                            prefs.childUserId = parcels[0].userId
                            prefs.childName = parcels[0].name
                            startActivity(Intent(this@LoginActivity, ParentalDashboardActivity::class.java))
                        } else {
                            val intent = Intent(this@LoginActivity, ChildSelectActivity::class.java)
                            intent.putParcelableArrayListExtra("children", parcels)
                            startActivity(intent)
                        }
                    } else {
                        body.childUserId?.let { prefs.childUserId = it }
                        startActivity(Intent(this@LoginActivity, ParentalDashboardActivity::class.java))
                    }
                    finish()
                } else {
                    Toast.makeText(this@LoginActivity, "Invalid PIN or not a parent account", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@LoginActivity, "Cannot reach server: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.btnLogin.isEnabled = true
                binding.progressBar.visibility = View.GONE
            }
        }
    }
}
