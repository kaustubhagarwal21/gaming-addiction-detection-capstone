package com.pes.parentmonitor.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.parentmonitor.BuildConfig
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.ModelCard
import com.pes.parentmonitor.databinding.ActivitySettingsBinding
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager
import com.pes.parentmonitor.util.PrivacyText
import com.pes.parentmonitor.util.ProfileValidation
import com.pes.parentmonitor.util.ServerOrigin
import com.pes.parentmonitor.util.ServerUrl
import com.pes.parentmonitor.util.SessionManager
import kotlinx.coroutines.CancellationException
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

        binding.btnSave.setOnClickListener {
            val normalized = ServerUrl.normalize(
                binding.etServerUrl.text?.toString(),
                BuildConfig.DEBUG
            )
            if (normalized == null) {
                binding.etServerUrl.error =
                    if (BuildConfig.DEBUG) {
                        "Enter a root HTTP(S) URL, for example http://192.168.1.2:5000/"
                    } else {
                        "Enter a root HTTPS URL (plain HTTP is allowed only for loopback)"
                    }
                return@setOnClickListener
            }
            binding.etServerUrl.error = null

            val originChanged = prefs.isLoggedIn() &&
                ServerOrigin.normalize(prefs.serverUrl) != ServerOrigin.normalize(normalized)
            if (originChanged) {
                // Deregister this device from the old backend before changing address.
                // A bearer token must never be reused at a different origin.
                SessionManager.logout(this, prefs)
            }
            prefs.serverUrl = normalized
            binding.etServerUrl.setText(normalized)
            updateProtectedActions()

            if (originChanged) {
                Toast.makeText(
                    this,
                    "Server changed. Sign in to the new server.",
                    Toast.LENGTH_LONG
                ).show()
                AuthNavigation.openLogin(this)
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

        binding.btnEditChild.setOnClickListener { editChildProfile() }

        binding.btnDeleteChildData.setOnClickListener { confirmDeleteChildData() }

        binding.btnRemoveChild.setOnClickListener { confirmRemoveChild() }

        binding.btnAboutModel.setOnClickListener { showModelCard() }

        updateProtectedActions()
    }

    override fun onResume() {
        super.onResume()
        updateProtectedActions()
    }

    /** Server/privacy/model information remains available before login; family data
     * controls are visible only for an authenticated parent with a selected child. */
    private fun updateProtectedActions() {
        val visible = if (prefs.isLoggedIn() && prefs.childUserId > 0) View.VISIBLE else View.GONE
        binding.btnEditChild.visibility = visible
        binding.btnDeleteChildData.visibility = visible
        binding.btnRemoveChild.visibility = visible
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
            } catch (e: CancellationException) {
                throw e
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

        // "Why trust this" — evidence measured on REAL data, in plain language.
        mc.chatMetricsGaming?.let { g ->
            g.atAlertThreshold?.let { t ->
                sb.append("\nChat alerts, tested on real in-game chat " +
                    "(${g.rows ?: 0} real messages): when a single message is flagged, " +
                    "it's right ${pct(t.precisionToxic)} of the time. Per-message alerts " +
                    "catch ${pct(t.recallToxic)} of toxic lines — repeated toxic language " +
                    "in one session raises an extra pattern alert on top.\n")
            }
        }
        mc.voiceMetrics?.let { v ->
            if ((v.model ?: "").contains("REAL", ignoreCase = true)) {
                sb.append("\nVoice emotion, tested on real recorded speech: " +
                    "${pct(v.accuracy)} accuracy across four emotions (guessing would be " +
                    "25%). It's a supporting signal and carries the lowest weight.\n")
            }
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

    /** Parent-only edit of the selected child's name, age, and (optional) login PIN.
        Pre-fills from the server so the parent sees current values; sends only fields
        that changed. All edits are parent-controlled server-side (age feeds the
        peer-comparison and time-limit cap, so it isn't child-editable). */
    private fun editChildProfile() {
        val childId = protectedChildId() ?: return
        lifecycleScope.launch {
            val api = ApiClient.getInstance(prefs.serverUrl)
            val profile = try {
                val response = api.getProfile(childId)
                response.takeIf { it.isSuccessful }?.body()
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                null
            }
            // Editing against a guessed/cached profile makes change detection unreliable
            // (and leaves age blank). Fail visibly instead of opening a form that cannot
            // faithfully represent the server state.
            if (profile == null) {
                Toast.makeText(this@SettingsActivity,
                    "Couldn't load the child's profile — try again when connected.",
                    Toast.LENGTH_LONG).show()
                return@launch
            }

            val pad = (16 * resources.displayMetrics.density).toInt()
            val nameField = android.widget.EditText(this@SettingsActivity).apply {
                hint = "Name"; setText(profile.name)
                inputType = android.text.InputType.TYPE_CLASS_TEXT or
                    android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS
            }
            val ageField = android.widget.EditText(this@SettingsActivity).apply {
                hint = "Age"; setText(profile.age?.toString() ?: "")
                inputType = android.text.InputType.TYPE_CLASS_NUMBER
            }
            val pinField = android.widget.EditText(this@SettingsActivity).apply {
                hint = "New child PIN (leave blank to keep)"
                inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                    android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            }
            val layout = android.widget.LinearLayout(this@SettingsActivity).apply {
                orientation = android.widget.LinearLayout.VERTICAL
                setPadding(pad, pad / 2, pad, 0)
                addView(nameField); addView(ageField); addView(pinField)
            }
            val dialog = AlertDialog.Builder(this@SettingsActivity)
                .setTitle("Edit Child Profile")
                .setView(layout)
                .setNegativeButton("Cancel", null)
                // Install the click listener after show(). AlertDialog's default positive
                // listener dismisses even when validation fails, losing everything typed.
                .setPositiveButton("Save", null)
                .create()
            dialog.setOnShowListener {
                dialog.getButton(android.content.DialogInterface.BUTTON_POSITIVE).setOnClickListener {
                    submitChildProfile(childId, nameField.text?.toString(),
                        ageField.text?.toString(), pinField.text?.toString(),
                        profile.name, profile.age, dialog)
                }
            }
            dialog.show()
        }
    }

    private fun submitChildProfile(childId: Int, rawName: String?, rawAge: String?,
                                   rawPin: String?, curName: String?, curAge: Int?,
                                   dialog: AlertDialog) {
        val nameRes = ProfileValidation.validateName(rawName)
        if (nameRes is ProfileValidation.Result.Error) {
            Toast.makeText(this, nameRes.message, Toast.LENGTH_SHORT).show(); return
        }
        val ageRes = ProfileValidation.validateAge(rawAge)
        if (ageRes is ProfileValidation.Result.Error) {
            Toast.makeText(this, ageRes.message, Toast.LENGTH_SHORT).show(); return
        }
        val pinRes = ProfileValidation.validateOptionalPin(rawPin)
        if (pinRes is ProfileValidation.Result.Error) {
            Toast.makeText(this, pinRes.message, Toast.LENGTH_SHORT).show(); return
        }
        val name = (nameRes as ProfileValidation.Result.Ok).value
        val age  = (ageRes as ProfileValidation.Result.Ok).value.toInt()
        val pin  = (pinRes as ProfileValidation.Result.Ok).value

        // Send only what changed; nothing changed → no round trip.
        val body = HashMap<String, Any>()
        body["user_id"] = childId
        if (name != curName) body["name"] = name
        if (age != curAge) body["age"] = age
        if (pin.isNotEmpty()) body["pin"] = pin
        if (body.size == 1) {
            Toast.makeText(this, "No changes", Toast.LENGTH_SHORT).show(); return
        }
        lifecycleScope.launch {
            val save = dialog.getButton(android.content.DialogInterface.BUTTON_POSITIVE)
            save.isEnabled = false
            try {
                val resp = ApiClient.getInstance(prefs.serverUrl).updateProfile(body)
                when {
                    resp.isSuccessful && resp.body()?.success == true -> {
                        if (body.containsKey("name")) prefs.childName = name  // keep the roster label fresh
                        Toast.makeText(this@SettingsActivity, "Profile updated", Toast.LENGTH_SHORT).show()
                        dialog.dismiss()
                    }
                    resp.code() == 409 ->
                        Toast.makeText(this@SettingsActivity, "That child PIN is already taken", Toast.LENGTH_LONG).show()
                    resp.code() == 400 ->
                        Toast.makeText(this@SettingsActivity,
                            "Check the name, age, and make sure the Child PIN differs from the Family PIN",
                            Toast.LENGTH_LONG).show()
                    else ->
                        Toast.makeText(this@SettingsActivity, "Update failed (${resp.code()})", Toast.LENGTH_LONG).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Update failed: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                if (dialog.isShowing) save.isEnabled = true
            }
        }
    }

    private fun confirmDeleteChildData() {
        val childId = protectedChildId() ?: return
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
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Delete failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun confirmRemoveChild() {
        val childId = protectedChildId() ?: return
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
                    // Stop the sticky poller before signing out, or it keeps "Guardian Active"
                    // running and polling the just-removed child until the app is killed.
                    SessionManager.logout(this@SettingsActivity, prefs)
                    startActivity(Intent(this@SettingsActivity, LoginActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
                    finish()
                } else {
                    Toast.makeText(this@SettingsActivity, "Remove failed (${resp.code()})", Toast.LENGTH_LONG).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Remove failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun testConnection() {
        val testUrl = ServerUrl.normalize(
            binding.etServerUrl.text?.toString(),
            BuildConfig.DEBUG
        )
        if (testUrl == null) {
            binding.etServerUrl.error = "Enter a valid root server URL first"
            return
        }
        binding.etServerUrl.error = null
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(testUrl)
                val resp = api.health()
                if (resp.isSuccessful) {
                    val modelsOk = if (resp.body()?.modelsLoaded == true) "Models OK" else "Models NOT loaded"
                    Toast.makeText(this@SettingsActivity, "Connected! $modelsOk", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@SettingsActivity, "Server error ${resp.code()}", Toast.LENGTH_SHORT).show()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@SettingsActivity, "Connection failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun protectedChildId(): Int? {
        if (!prefs.isLoggedIn()) {
            Toast.makeText(this, "Sign in to manage family data", Toast.LENGTH_SHORT).show()
            AuthNavigation.openLogin(this)
            return null
        }
        return prefs.childUserId.takeIf { it > 0 } ?: run {
            Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            null
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
