package com.pes.gamingdetector.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.BuildConfig
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivitySettingsBinding
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.PrivacyText
import com.pes.gamingdetector.util.ServerUrl
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

class SettingsActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivitySettingsBinding
    private lateinit var prefs: PrefsManager

    override fun authenticationRequired(): Boolean =
        !intent.getBooleanExtra(EXTRA_SERVER_SETUP_ONLY, false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!ensureAuthenticatedOnCreate()) return
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        val setupOnly = intent.getBooleanExtra(EXTRA_SERVER_SETUP_ONLY, false)
        val parentUnlocked = intent.getBooleanExtra(EXTRA_PARENT_UNLOCKED, false)
        // SettingsActivity is internal, but still enforce the entry contract here. The
        // login-screen developer path may configure only the endpoint; family/game
        // controls require the server-verified parent-PIN path from HomeActivity.
        if ((!setupOnly && !parentUnlocked) || (setupOnly && prefs.isLoggedIn())) {
            finish()
            return
        }

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Settings"

        // Family code — permanently visible here so it can't be forgotten (it otherwise
        // appears only once, in the registration dialog). Tap the code to copy it.
        val code = prefs.familyCode
        if (parentUnlocked && code.isNotBlank()) {
            binding.cardFamilyCode.visibility = android.view.View.VISIBLE
            binding.tvFamilyCode.text = code
            binding.tvFamilyCode.setOnClickListener {
                val cb = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                cb.setPrimaryClip(android.content.ClipData.newPlainText("Family code", code))
                Toast.makeText(this, "Family code copied", Toast.LENGTH_SHORT).show()
            }
        }

        binding.etServerUrl.setText(prefs.serverUrl)

        binding.btnSaveUrl.setOnClickListener {
            val normalized = validatedInput() ?: return@setOnClickListener
            if (prefs.isLoggedIn() && normalized != prefs.serverUrl) {
                // Reusing an old server's bearer token at a new origin leaks credentials
                // and creates a split local/server session. Change only before login.
                Toast.makeText(this,
                    "Sign out before changing the server URL.", Toast.LENGTH_LONG).show()
            } else {
                prefs.serverUrl = normalized
                binding.etServerUrl.setText(normalized)
                Toast.makeText(this, "Server URL saved", Toast.LENGTH_SHORT).show()
            }
        }

        binding.btnTestConnection.setOnClickListener { testConnection() }

        binding.btnPrivacyPolicy.setOnClickListener {
            AlertDialog.Builder(this)
                .setTitle("Privacy Policy")
                .setMessage(PrivacyText.POLICY)
                .setPositiveButton("Close", null)
                .show()
        }

        binding.btnManageGames.visibility = if (parentUnlocked) View.VISIBLE else View.GONE
        if (parentUnlocked) {
            binding.btnManageGames.setOnClickListener {
                startActivity(Intent(this, ManageGamesActivity::class.java))
            }
        }

        // Dual-language STT toggle is a monitoring-behaviour change, so it is
        // parent-gated like game management. Takes effect from the next session's
        // recorder start (the running recorder is not restarted mid-session).
        binding.switchHindiStt.visibility = if (parentUnlocked) View.VISIBLE else View.GONE
        binding.switchHindiStt.isChecked = prefs.hindiVoiceStt
        binding.switchHindiStt.setOnCheckedChangeListener { _, checked ->
            prefs.hindiVoiceStt = checked
        }
    }

    private fun testConnection() {
        val url = validatedInput() ?: return
        lifecycleScope.launch {
            try {
                // Test what is currently typed, not the previously saved endpoint.
                val api = ApiClient.getInstance(url)
                val resp = api.health()
                if (resp.isSuccessful) {
                    val body = resp.body()
                    val modelsOk = if (body?.modelsLoaded == true) "Models OK" else "Models NOT loaded"
                    Toast.makeText(this@SettingsActivity, "Connected! $modelsOk", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@SettingsActivity, "Server returned error ${resp.code()}", Toast.LENGTH_SHORT).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Connection failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun validatedInput(): String? {
        val normalized = ServerUrl.normalize(
            binding.etServerUrl.text?.toString().orEmpty(),
            allowInsecureLan = BuildConfig.DEBUG
        )
        if (normalized == null) {
            binding.etServerUrl.error = if (BuildConfig.DEBUG)
                "Enter an http(s) base URL without credentials/query"
            else
                "Use HTTPS (or a loopback development URL)"
        } else {
            binding.etServerUrl.error = null
        }
        return normalized
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    companion object {
        const val EXTRA_SERVER_SETUP_ONLY = "server_setup_only"
        const val EXTRA_PARENT_UNLOCKED = "parent_unlocked"
    }
}
