package com.pes.gamingdetector.activities

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.api.RegisterRequest
import com.pes.gamingdetector.databinding.ActivityRegisterBinding
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.launch

/**
 * First-time account setup for a real family. The parent fills this in on the child's
 * device: the child gets their own login PIN, and a shared Family PIN groups siblings
 * under one parent (who logs into the Parent app with that Family PIN). On success the
 * child is signed in immediately and lands on Home (which then asks for consent).
 */
class RegisterActivity : AppCompatActivity() {
    private lateinit var binding: ActivityRegisterBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityRegisterBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Create account"

        binding.btnRegister.setOnClickListener { doRegister() }
        binding.tvBackToLogin.setOnClickListener { finish() }
    }

    private fun doRegister() {
        val name       = binding.etName.text.toString().trim()
        val age        = binding.etAge.text.toString().trim().toIntOrNull()
        val childPin   = binding.etChildPin.text.toString().trim()
        val familyPin  = binding.etFamilyPin.text.toString().trim()
        val familyCode = binding.etFamilyCode.text.toString().trim().uppercase()

        // Client-side checks mirror the server so the user gets instant feedback.
        when {
            name.isEmpty() -> { binding.etName.error = "Enter the child's name"; return }
            age == null || age !in 1..100 -> { binding.etAge.error = "Enter a valid age"; return }
            childPin.length !in 4..6 -> { binding.etChildPin.error = "4–6 digits"; return }
            familyPin.length !in 4..6 -> { binding.etFamilyPin.error = "4–6 digits"; return }
            childPin == familyPin -> { binding.etFamilyPin.error = "Must differ from the child PIN"; return }
        }

        binding.btnRegister.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api  = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.register(
                    RegisterRequest(name, age!!, childPin, familyPin, familyCode.ifBlank { null }))
                val body = resp.body()
                if (resp.isSuccessful && body?.success == true) {
                    prefs.authToken = body.token   // set first so following calls are authenticated
                    prefs.userId    = body.userId
                    prefs.userName  = body.name
                    // Show the family code (so the parent knows what to enter in the
                    // Parent app), then continue to Home.
                    showFamilyCodeThenHome(body.name, body.familyCode, joined = familyCode.isNotBlank())
                } else {
                    // 4xx (e.g. PIN taken) puts the message in errorBody, not body.
                    val msg = body?.message ?: serverMessage(resp) ?: "Couldn't create account (${resp.code()})"
                    Toast.makeText(this@RegisterActivity, msg, Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@RegisterActivity, "Cannot reach server: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.btnRegister.isEnabled = true
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    /** Show the family code after registration so the parent can use it in the Parent
        app, then move on to Home. New families get a generated code to write down;
        siblings just confirm they joined. */
    private fun showFamilyCodeThenHome(name: String, code: String?, joined: Boolean) {
        if (code.isNullOrBlank()) { goHome(); return }
        val title = if (joined) "Account created" else "Family created"
        val msg = if (joined)
            "Welcome, $name! This child was added to family $code."
        else
            "Welcome, $name!\n\nYour family code is:\n\n$code\n\n" +
            "In the Parent app, sign in with this code + your Family PIN to see this child. " +
            "Use the same family code when setting up siblings."
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(msg)
            .setCancelable(false)
            .setPositiveButton("Continue") { _, _ -> goHome() }
            .show()
    }

    private fun goHome() {
        startActivity(Intent(this, HomeActivity::class.java))
        finishAffinity()   // clear the auth stack; Home is the new root
    }

    /** Pull the server's human-readable message out of a non-2xx error body. */
    private fun serverMessage(resp: retrofit2.Response<*>): String? = try {
        resp.errorBody()?.string()?.takeIf { it.isNotBlank() }?.let {
            org.json.JSONObject(it).optString("message").ifBlank { null }
        }
    } catch (_: Exception) { null }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
