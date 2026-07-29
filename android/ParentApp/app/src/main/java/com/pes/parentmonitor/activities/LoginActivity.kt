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
import com.pes.parentmonitor.service.FcmTokenSyncWorker
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.CancellationException
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
        // The cached token is useful immediately; token retrieval below may take time.
        prefs.fcmToken.takeIf { it.isNotBlank() }?.let {
            FcmTokenSyncWorker.enqueueRegistration(this, it)
        }
        try {
            FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
                if (token.isNullOrEmpty()) return@addOnSuccessListener
                prefs.fcmToken = token
                // The Login Activity finishes immediately after this callback is
                // registered, so lifecycleScope work was often cancelled. WorkManager
                // persists the update and retries it when the network returns.
                FcmTokenSyncWorker.enqueueRegistration(applicationContext, token)
            }
        } catch (_: Exception) {
            // Firebase not configured — FCM push disabled, polling still works
        }
    }

    private fun doLogin() {
        val familyCode = binding.etFamilyCode.text.toString().trim().uppercase()
        if (familyCode.isEmpty()) {
            binding.etFamilyCode.error = "Enter your family code"
            return
        }
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
                val resp = api.login(
                    LoginRequest(pin = pin, role = "parent", familyCode = familyCode))
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val body = resp.body()!!
                    val token = body.token?.trim()?.takeIf { it.isNotEmpty() }
                    if (token == null || body.userId <= 0 ||
                        !body.role.equals("parent", ignoreCase = true)
                    ) {
                        Toast.makeText(
                            this@LoginActivity,
                            "Server returned an invalid login session",
                            Toast.LENGTH_LONG
                        ).show()
                        return@launch
                    }
                    // Bind future data-only pushes to this family. If an older backend
                    // omits the field, push is ignored safely and polling remains active.
                    prefs.familyCode = body.familyCode.orEmpty()
                    prefs.authToken = token   // set first so following calls are authenticated
                    prefs.parentId = body.userId
                    prefs.parentName = body.name
                    registerFcmToken(prefs)

                    val children = body.children
                    if (!children.isNullOrEmpty()) {
                        val parcels = ArrayList(children.map {
                            ChildSelectActivity.ChildInfoParcel(it.userId, it.name, it.age)
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
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@LoginActivity, "Cannot reach server: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.btnLogin.isEnabled = true
                binding.progressBar.visibility = View.GONE
            }
        }
    }
}
