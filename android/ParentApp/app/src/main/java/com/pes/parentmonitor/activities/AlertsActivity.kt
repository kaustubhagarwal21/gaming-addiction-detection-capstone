package com.pes.parentmonitor.activities

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.pes.parentmonitor.R
import com.pes.parentmonitor.api.Alert
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.api.MarkReadRequest
import com.pes.parentmonitor.databinding.ActivityAlertsBinding
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.launch

class AlertsActivity : AppCompatActivity() {
    private lateinit var binding: ActivityAlertsBinding
    private lateinit var prefs: PrefsManager
    private val alerts = mutableListOf<Alert>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityAlertsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Alerts"

        binding.rvAlerts.layoutManager = LinearLayoutManager(this)
        binding.rvAlerts.adapter = AlertAdapter()

        binding.swipeRefresh.setOnRefreshListener { loadAlerts() }
        loadAlerts()
    }

    private fun loadAlerts() {
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getAlerts(prefs.childUserId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val body = resp.body()!!
                    alerts.clear()
                    alerts.addAll(body.alerts ?: emptyList())
                    binding.rvAlerts.adapter?.notifyDataSetChanged()
                    binding.tvEmpty.visibility = if (alerts.isEmpty()) View.VISIBLE else View.GONE

                    val unreadIds = alerts.filter { !it.read }.map { it.id }
                    if (unreadIds.isNotEmpty()) {
                        api.markAlertsRead(MarkReadRequest(unreadIds))
                    }
                }
            } catch (e: Exception) {
                Toast.makeText(this@AlertsActivity, "Failed to load alerts", Toast.LENGTH_SHORT).show()
            } finally {
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private inner class AlertAdapter : RecyclerView.Adapter<AlertAdapter.VH>() {
        inner class VH(v: View) : RecyclerView.ViewHolder(v) {
            val tvMessage: TextView = v.findViewById(R.id.tvAlertMessage)
            val tvTime: TextView = v.findViewById(R.id.tvAlertTime)
            val tvSeverity: TextView = v.findViewById(R.id.tvAlertSeverity)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_alert, parent, false)
            return VH(v)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            val alert = alerts[position]
            holder.tvMessage.text = alert.message
            holder.tvTime.text = alert.createdAt
            holder.tvSeverity.text = alert.severity.uppercase()
            val color = when (alert.severity.lowercase()) {
                "high" -> getColor(R.color.risk_high)
                "medium" -> getColor(R.color.risk_medium)
                else -> getColor(R.color.risk_low)
            }
            holder.tvSeverity.setTextColor(color)
            if (!alert.read) {
                holder.itemView.setBackgroundColor(color and 0x22FFFFFF)
            }
        }

        override fun getItemCount() = alerts.size
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}
