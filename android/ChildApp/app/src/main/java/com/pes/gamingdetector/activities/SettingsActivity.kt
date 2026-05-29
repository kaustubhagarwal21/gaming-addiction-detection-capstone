package com.pes.gamingdetector.activities

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivitySettingsBinding
import com.pes.gamingdetector.util.PrefsManager
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

        val uid = prefs.userId
        if (uid != -1) {
            binding.tvPairingCode.text = uid.toString().padStart(6, '0')
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
