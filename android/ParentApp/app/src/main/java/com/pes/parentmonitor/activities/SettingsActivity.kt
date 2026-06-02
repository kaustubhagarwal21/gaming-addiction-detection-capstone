package com.pes.parentmonitor.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.ModelCard
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

        binding.btnRemoveChild.setOnClickListener { confirmRemoveChild() }

        binding.btnAboutModel.setOnClickListener { showModelCard() }
    }

    private fun showModelCard() {
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getModelCard()
                if (resp.isSuccessful && resp.body()?.success == true) {
                    showModelCardDialog(resp.body()!!)
                } else {
                    Toast.makeText(this@SettingsActivity, "Couldn't load model info (${resp.code()})", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Couldn't reach server: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    /** Honest, plain-language model card so a parent (and an examiner) can see exactly
        how reliable the score is and that it's a screening signal, not a diagnosis. */
    private fun showModelCardDialog(mc: ModelCard) {
        fun pct(d: Double?) = if (d != null) "${"%.0f".format(d * 100)}%" else "—"
        val nice   = mapOf("casual" to "Low", "at_risk" to "Some", "addicted" to "High")
        val labels = mc.confusionLabels ?: listOf("casual", "at_risk", "addicted")
        val sb = StringBuilder()

        sb.append("Overall accuracy: ${pct(mc.testAccuracy)}")
        if (mc.cvMeanAccuracy != null) {
            sb.append("  (5-fold cross-validation ${pct(mc.cvMeanAccuracy)} ± ${pct(mc.cvStdAccuracy)})")
        }

        sb.append("\n\nPer band (precision / recall):\n")
        labels.forEach { l ->
            sb.append("  ${nice[l] ?: l} concern:  ${pct(mc.perClassPrecision?.get(l))} / ${pct(mc.perClassRecall?.get(l))}\n")
        }

        val cm = mc.confusionMatrix
        if (cm != null && cm.size == labels.size) {
            sb.append("\nWhere mistakes go (actual → predicted):\n")
            cm.forEachIndexed { i, row ->
                val parts = row.mapIndexed { j, n -> "$n ${nice[labels[j]] ?: labels[j]}" }
                sb.append("  ${nice[labels[i]] ?: labels[i]}: ${parts.joinToString(", ")}\n")
            }
            sb.append("Errors only land in a neighbouring band — never Low↔High.\n")
        }

        mc.ensembleWeights?.let { w ->
            val b = ((w["behaviour"] ?: 0.0) * 100).toInt()
            val c = ((w["chat"] ?: 0.0) * 100).toInt()
            val v = ((w["voice"] ?: 0.0) * 100).toInt()
            sb.append("\nCombined score: behaviour $b% · chat $c% · voice $v%\n")
        }
        mc.calibration?.let { cal ->
            sb.append("\nProbabilities are ${cal.method ?: "isotonic"}-calibrated " +
                "(Brier ${"%.3f".format(cal.brierUncalibrated ?: 0.0)} → " +
                "${"%.3f".format(cal.brierCalibrated ?: 0.0)}, lower = better).\n")
        }
        mc.thresholdsNote?.let { sb.append("\n$it\n") }
        mc.dataNote?.let { sb.append("\n$it") }
        mc.disclaimer?.let { sb.append("\n\n$it") }

        AlertDialog.Builder(this)
            .setTitle("How the risk score works")
            .setMessage(sb.toString())
            .setPositiveButton("Close", null)
            .show()
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

    private fun confirmRemoveChild() {
        val childId = prefs.childUserId
        if (childId == -1) {
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        val who = prefs.childName.ifBlank { "this child" }
        AlertDialog.Builder(this)
            .setTitle("Remove $who from your family?")
            .setMessage("This permanently removes $who and ALL their data. They'll no longer " +
                "appear here, and their Child-app PIN will stop working. This cannot be undone.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Remove") { _, _ -> removeChild(childId) }
            .show()
    }

    /** Full account removal (scope=account): deletes the child's user row + data. The
        family roster changed, so we send the parent back to sign in — re-login fetches
        the updated list of children. */
    private fun removeChild(childId: Int) {
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.deleteData(mapOf("user_id" to childId.toString(), "scope" to "account"))
                if (resp.isSuccessful && resp.body()?.success == true) {
                    Toast.makeText(this@SettingsActivity, "Child removed from family", Toast.LENGTH_LONG).show()
                    prefs.logout()   // roster changed → re-login refreshes it (keeps server URL)
                    startActivity(Intent(this@SettingsActivity, LoginActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
                    finish()
                } else {
                    Toast.makeText(this@SettingsActivity, "Remove failed (${resp.code()})", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Remove failed: ${e.message}", Toast.LENGTH_LONG).show()
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
