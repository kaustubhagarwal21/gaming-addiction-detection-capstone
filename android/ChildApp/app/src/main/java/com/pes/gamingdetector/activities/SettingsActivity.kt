package com.pes.gamingdetector.activities

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivitySettingsBinding
import com.pes.gamingdetector.util.PrefsManager
import com.pes.gamingdetector.util.PrivacyText
import kotlinx.coroutines.launch

class SettingsActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySettingsBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Settings"

        binding.etServerUrl.setText(prefs.serverUrl)

        binding.btnSaveUrl.setOnClickListener {
            val url = binding.etServerUrl.text.toString().trim()
            if (url.isNotEmpty()) {
                val normalized = if (url.endsWith("/")) url else "$url/"
                prefs.serverUrl = normalized
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

        binding.btnDeleteData.setOnClickListener { confirmDeleteData() }

        val uid = prefs.userId
        if (uid != -1) {
            binding.tvPairingCode.text = uid.toString().padStart(6, '0')
        }
    }

    private fun confirmDeleteData() {
        AlertDialog.Builder(this)
            .setTitle("Delete My Data?")
            .setMessage("This permanently erases all your sessions, chats, voice analysis, " +
                "predictions and alerts. This cannot be undone.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Delete") { _, _ -> deleteData() }
            .show()
    }

    private fun deleteData() {
        val uid = prefs.userId
        if (uid == -1) return
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.deleteData(mapOf("user_id" to uid.toString(), "scope" to "data"))
                val msg = if (resp.isSuccessful) "Your data has been deleted"
                          else "Delete failed (${resp.code()})"
                Toast.makeText(this@SettingsActivity, msg, Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Delete failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun testConnection() {
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.health()
                if (resp.isSuccessful) {
                    val body = resp.body()
                    val modelsOk = if (body?.modelsLoaded == true) "Models OK" else "Models NOT loaded"
                    Toast.makeText(this@SettingsActivity, "Connected! $modelsOk", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@SettingsActivity, "Server returned error ${resp.code()}", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Connection failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
