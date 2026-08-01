package com.pes.parentmonitor.activities

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.pes.parentmonitor.R
import com.pes.parentmonitor.api.Alert
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.FeedbackRequest
import com.pes.parentmonitor.api.MarkReadRequest
import com.pes.parentmonitor.databinding.ActivityAlertsBinding
import com.pes.parentmonitor.util.AlertTriage
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.Constants
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

class AlertsActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivityAlertsBinding
    private lateinit var prefs: PrefsManager
    private val alerts = mutableListOf<Alert>()
    private var loadJob: Job? = null
    private var loadGeneration = 0
    private var displayedChildId = -1

    // Auto-refresh while the screen is open so new alerts appear without a manual pull.
    private val uiHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val REFRESH_MS = 15_000L
    private val autoRefresh = object : Runnable {
        override fun run() {
            loadAlerts(silent = true)
            uiHandler.postDelayed(this, REFRESH_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityAlertsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Alerts"
        applyNotificationTarget(intent)

        binding.rvAlerts.layoutManager = LinearLayoutManager(this)
        binding.rvAlerts.adapter = AlertAdapter()

        binding.swipeRefresh.setOnRefreshListener { loadAlerts() }
    }

    override fun onAuthenticatedResume() {
        loadAlerts()
        uiHandler.removeCallbacks(autoRefresh)
        uiHandler.postDelayed(autoRefresh, REFRESH_MS)
    }

    override fun onPause() {
        super.onPause()
        uiHandler.removeCallbacks(autoRefresh)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (!AuthNavigation.ensureAuthenticated(this, prefs)) return
        if (applyNotificationTarget(intent)) {
            loadJob?.cancel()
            alerts.clear()
            binding.rvAlerts.adapter?.notifyDataSetChanged()
            binding.tvFeedbackSummary.visibility = View.GONE
            loadAlerts()
        }
    }

    /** Select the child named by a push/poll notification before fetching alerts. */
    private fun applyNotificationTarget(source: Intent): Boolean {
        val childId = source.getIntExtra(Constants.EXTRA_CHILD_USER_ID, -1)
        if (childId <= 0) return false
        val changed = childId != prefs.childUserId
        prefs.childUserId = childId
        source.getStringExtra(Constants.EXTRA_CHILD_NAME)
            ?.takeIf { it.isNotBlank() }
            ?.let { prefs.childName = it }
        supportActionBar?.title = prefs.childName.takeIf { it.isNotBlank() }
            ?.let { "Alerts · $it" } ?: "Alerts"
        return changed
    }

    private fun loadAlerts(silent: Boolean = false) {
        if (silent && loadJob?.isActive == true) return
        if (!silent) loadJob?.cancel()
        val generation = ++loadGeneration
        val childId = prefs.childUserId
        val serverUrl = prefs.serverUrl
        prepareForChild(childId)
        if (childId <= 0) {
            binding.swipeRefresh.isRefreshing = false
            if (!silent) Toast.makeText(this, "No child selected", Toast.LENGTH_SHORT).show()
            return
        }
        loadJob = lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(serverUrl)
                val resp = api.getAlerts(childId)
                if (generation != loadGeneration || childId != prefs.childUserId) return@launch
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val body = resp.body()!!
                    val incoming = body.alerts ?: emptyList()
                    // On a silent auto-tick, only touch the list when it actually changed
                    // (avoids flicker / losing scroll position while the parent reads).
                    // Compare id + feedback + read so a row marked read server-side also
                    // refreshes (drops its unread highlight) on the next tick.
                    val changed = incoming != alerts
                    if (!silent || changed) {
                        alerts.clear()
                        alerts.addAll(incoming)
                        binding.rvAlerts.adapter?.notifyDataSetChanged()
                        binding.tvEmpty.visibility = if (alerts.isEmpty()) View.VISIBLE else View.GONE
                    }
                    val unreadIds = incoming.filter { !it.read }.map { it.id }
                    if (unreadIds.isNotEmpty()) {
                        // The endpoint accepts at most 100 ids per call, so a backlog
                        // larger than that used to fail the whole request with a 400 and
                        // leave the badge stuck forever. Send it in chunks.
                        var allMarked = true
                        for (batch in unreadIds.chunked(100)) {
                            val marked = api.markAlertsRead(MarkReadRequest(batch))
                            if (generation != loadGeneration || childId != prefs.childUserId) {
                                return@launch
                            }
                            if (!(marked.isSuccessful && marked.body()?.success == true)) {
                                allMarked = false
                                break
                            }
                        }
                        if (allMarked) {
                            val ids = unreadIds.toHashSet()
                            alerts.filter { it.id in ids }.forEach { it.read = true }
                            binding.rvAlerts.adapter?.notifyDataSetChanged()
                        }
                    }
                }
                loadFeedbackSummary(api, childId, generation)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (!silent) Toast.makeText(this@AlertsActivity, "Failed to load alerts", Toast.LENGTH_SHORT).show()
            } finally {
                if (generation == loadGeneration) {
                    if (!silent) binding.swipeRefresh.isRefreshing = false
                    loadJob = null
                }
            }
        }
    }

    private fun prepareForChild(childId: Int) {
        if (displayedChildId == childId) return
        displayedChildId = childId
        loadJob?.cancel()
        alerts.clear()
        binding.rvAlerts.adapter?.notifyDataSetChanged()
        binding.tvEmpty.visibility = View.VISIBLE
        binding.tvFeedbackSummary.visibility = View.GONE
        supportActionBar?.title = prefs.childName.takeIf { it.isNotBlank() }
            ?.let { "Alerts · $it" } ?: "Alerts"
    }

    /** Surface the agreement rate built from the parent's own verdicts — the system's
     *  real-world accuracy signal — once at least one verdict exists. */
    private suspend fun loadFeedbackSummary(
        api: com.pes.parentmonitor.api.ApiService,
        childId: Int,
        generation: Int
    ) {
        try {
            val resp = api.getFeedbackSummary(childId)
            if (generation != loadGeneration || childId != prefs.childUserId) return
            val body = resp.body()
            val acc  = body?.counts?.get("accurate") ?: 0
            val fa   = body?.counts?.get("false_alarm") ?: 0
            val rate = body?.agreementRate
            if (resp.isSuccessful && body?.success == true && rate != null && acc + fa > 0) {
                val n = acc + fa
                binding.tvFeedbackSummary.text =
                    "📊 Based on your ${n} verdict${if (n == 1) "" else "s"}, you've rated the " +
                    "model accurate ${"%.0f".format(rate * 100)}% of the time. " +
                    "Keep rating alerts — it helps tune future versions."
                binding.tvFeedbackSummary.visibility = View.VISIBLE
            } else {
                binding.tvFeedbackSummary.visibility = View.GONE
            }
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            // Summary is optional — leave hidden.
        }
    }

    /** "Just now" / "12m ago" / "3h ago" / "2d ago", from the server-computed age (the
     *  raw created_at is in the server's clock and can't be diffed on the device). */
    private fun friendlyAge(alert: Alert): String {
        val m = alert.ageMinutes ?: return alert.createdAt.take(16).replace('T', ' ')
        return when {
            m < 1        -> "Just now"
            m < 60       -> "${m}m ago"
            m < 24 * 60  -> "${m / 60}h ago"
            m < 7 * 24 * 60 -> "${m / (24 * 60)}d ago"
            else         -> alert.createdAt.take(10)
        }
    }

    private inner class AlertAdapter : RecyclerView.Adapter<AlertAdapter.VH>() {
        inner class VH(v: View) : RecyclerView.ViewHolder(v) {
            val tvMessage: TextView = v.findViewById(R.id.tvAlertMessage)
            val tvTime: TextView = v.findViewById(R.id.tvAlertTime)
            val tvSeverity: TextView = v.findViewById(R.id.tvAlertSeverity)
            val feedbackPrompt: LinearLayout = v.findViewById(R.id.feedbackPrompt)
            val btnAccurate: MaterialButton = v.findViewById(R.id.btnAccurate)
            val btnFalseAlarm: MaterialButton = v.findViewById(R.id.btnFalseAlarm)
            val tvFeedbackGiven: TextView = v.findViewById(R.id.tvFeedbackGiven)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_alert, parent, false)
            return VH(v)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            val alert = alerts[position]
            holder.tvMessage.text = alert.message
            holder.tvTime.text = friendlyAge(alert)
            holder.tvSeverity.text = alert.severity.uppercase()
            val color = when (alert.severity.lowercase()) {
                "high" -> getColor(R.color.risk_high)
                "medium" -> getColor(R.color.risk_medium)
                else -> getColor(R.color.risk_low)
            }
            holder.tvSeverity.setTextColor(color)
            // Always set both branches — recycled rows otherwise keep a previous
            // alert's unread tint (stale highlight on scrolled lists).
            if (!alert.read) {
                holder.itemView.setBackgroundColor(color and 0x22FFFFFF)
            } else {
                holder.itemView.setBackgroundColor(android.graphics.Color.TRANSPARENT)
            }
            bindFeedback(holder, alert)
        }

        private fun bindFeedback(holder: VH, alert: Alert) {
            // "Was this accurate?" feedback only makes sense for model assessments.
            // This includes aggregate toxicity streaks and late risk revisions;
            // informational alerts like "started playing" carry no judgement to rate.
            if (!AlertTriage.isFeedbackEligible(alert.type)) {
                holder.feedbackPrompt.visibility = View.GONE
                holder.tvFeedbackGiven.visibility = View.GONE
                return
            }
            val given = alert.feedback
            if (given != null) {
                holder.feedbackPrompt.visibility = View.GONE
                holder.tvFeedbackGiven.visibility = View.VISIBLE
                holder.tvFeedbackGiven.text = when (given) {
                    "accurate"    -> "✓ You marked this accurate — thanks"
                    "false_alarm" -> "✗ You marked this a false alarm — thanks"
                    else          -> "Feedback recorded: $given"
                }
            } else {
                holder.feedbackPrompt.visibility = View.VISIBLE
                holder.tvFeedbackGiven.visibility = View.GONE
                holder.btnAccurate.isEnabled = true        // reset recycled state
                holder.btnFalseAlarm.isEnabled = true
                holder.btnAccurate.setOnClickListener {
                    holder.btnAccurate.isEnabled = false
                    holder.btnFalseAlarm.isEnabled = false
                    sendFeedback(alert.id, "accurate")
                }
                holder.btnFalseAlarm.setOnClickListener {
                    holder.btnAccurate.isEnabled = false
                    holder.btnFalseAlarm.isEnabled = false
                    sendFeedback(alert.id, "false_alarm")
                }
            }
        }

        override fun getItemCount() = alerts.size
    }

    private fun sendFeedback(alertId: Int, label: String) {
        val childId = prefs.childUserId
        val serverUrl = prefs.serverUrl
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(serverUrl)
                val resp = api.submitFeedback(
                    FeedbackRequest(userId = childId, alertId = alertId, label = label)
                )
                if (childId != prefs.childUserId) return@launch
                val index = alerts.indexOfFirst { it.id == alertId }
                if (resp.isSuccessful && resp.body()?.success == true && index >= 0) {
                    alerts[index].feedback = label
                    binding.rvAlerts.adapter?.notifyItemChanged(index)
                } else {
                    Toast.makeText(this@AlertsActivity, "Couldn't save feedback", Toast.LENGTH_SHORT).show()
                    if (index >= 0) binding.rvAlerts.adapter?.notifyItemChanged(index)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@AlertsActivity, "Couldn't save feedback", Toast.LENGTH_SHORT).show()
                val index = alerts.indexOfFirst { it.id == alertId }
                if (index >= 0) binding.rvAlerts.adapter?.notifyItemChanged(index)
            }
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
