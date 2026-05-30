package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.databinding.ActivitySettingsBinding
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.PrivacyText
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
        binding.etChildUserId.setText(if (prefs.childUserId != -1) prefs.childUserId.toString() else "")

        binding.btnSave.setOnClickListener {
            val url     = binding.etServerUrl.text.toString().trim()
            val childId = binding.etChildUserId.text.toString().trim().toIntOrNull()

            if (url.isNotEmpty()) {
                prefs.serverUrl = if (url.endsWith("/")) url else "$url/"
            }
            if (childId != null) {
                prefs.childUserId = childId
                attemptPairing(childId)
            } else {
                Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
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

        binding.btnDeleteChildData.setOnClickListener { confirmDeleteChildData() }
    }

    private fun confirmDeleteChildData() {
        val childId = prefs.childUserId
        if (childId == -1) {
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Delete This Child's Data?")
            .setMessage("This permanently erases all collected sessions, chats, voice analysis, " +
                "predictions and alerts for this child. This cannot be undone.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Delete") { _, _ -> deleteChildData(childId) }
            .show()
    }

    private fun deleteChildData(childId: Int) {
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.deleteData(mapOf("user_id" to childId.toString(), "scope" to "data"))
                val msg = if (resp.isSuccessful) "Child's data has been deleted"
                          else "Delete failed (${resp.code()})"
                Toast.makeText(this@SettingsActivity, msg, Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Delete failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun attemptPairing(childId: Int) {
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val body = mapOf("parent_id" to prefs.parentId, "child_user_id" to childId)
                val resp = api.pairDevices(body)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val name = resp.body()?.childName ?: "your child"
                    binding.tvPairedStatus.text = "Paired with: $name (ID: $childId)"
                    binding.tvPairedStatus.visibility = View.VISIBLE
                    Toast.makeText(this@SettingsActivity, "Paired with $name", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@SettingsActivity, "Pairing failed — check the code", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Settings saved (pairing skipped: ${e.message})", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun testConnection() {
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.health()
                if (resp.isSuccessful) {
                    val modelsOk = if (resp.body()?.modelsLoaded == true) "Models OK" else "Models NOT loaded"
                    Toast.makeText(this@SettingsActivity, "Connected! $modelsOk", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@SettingsActivity, "Server error ${resp.code()}", Toast.LENGTH_SHORT).show()
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
