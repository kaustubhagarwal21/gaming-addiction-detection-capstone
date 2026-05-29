package com.pes.gamingdetector.activities

import android.graphics.Color
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
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.databinding.ActivitySessionHistoryBinding
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Locale

class SessionHistoryActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySessionHistoryBinding
    private lateinit var prefs: PrefsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySessionHistoryBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Session History"

        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.swipeRefresh.setOnRefreshListener { loadHistory() }
        loadHistory()
    }

    private fun loadHistory() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getSessions(prefs.userId)
                if (resp.isSuccessful) {
                    val sessions = resp.body() ?: emptyList()
                    if (sessions.isEmpty()) {
                        binding.tvEmpty.visibility = View.VISIBLE
                        binding.recyclerView.visibility = View.GONE
                    } else {
                        binding.tvEmpty.visibility = View.GONE
                        binding.recyclerView.visibility = View.VISIBLE
                        binding.recyclerView.adapter = SessionAdapter(sessions)
                    }
                }
            } catch (e: Exception) {
                Toast.makeText(this@SessionHistoryActivity, "Load failed: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                binding.progressBar.visibility = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    override fun onSupportNavigateUp(): Boolean { finish(); return true }

    inner class SessionAdapter(private val items: List<com.pes.gamingdetector.api.SessionRow>)
        : RecyclerView.Adapter<SessionAdapter.VH>() {

        inner class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val dot      = itemView.findViewById<View>(R.id.riskDot)
            val game     = itemView.findViewById<TextView>(R.id.tvGameName)
            val date     = itemView.findViewById<TextView>(R.id.tvSessionDate)
            val duration = itemView.findViewById<TextView>(R.id.tvDuration)
            val badge    = itemView.findViewById<TextView>(R.id.tvRiskBadge)
        }

        override fun onCreateViewHolder(p: ViewGroup, t: Int) =
            VH(LayoutInflater.from(p.context).inflate(R.layout.item_session, p, false))

        override fun getItemCount() = items.size

        override fun onBindViewHolder(h: VH, pos: Int) {
            val s = items[pos]
            h.game.text = s.gameName ?: "Unknown Game"

            val rawDate = s.startTime ?: ""
            h.date.text = try {
                val inFmt  = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
                val outFmt = SimpleDateFormat("MMM d, yyyy  h:mm a", Locale.getDefault())
                outFmt.format(inFmt.parse(rawDate)!!)
            } catch (e: Exception) { rawDate }

            val secs = s.durationSeconds ?: 0
            val mins = secs / 60
            h.duration.text = if (mins >= 60) "${mins / 60}h ${mins % 60}m" else "${mins}m"

            val risk  = s.riskCategory?.lowercase() ?: "casual"
            val color = when (risk) {
                "addicted" -> getColor(R.color.risk_high)
                "at_risk"  -> getColor(R.color.risk_medium)
                else       -> getColor(R.color.risk_low)
            }
            h.dot.background.setTint(color)
            h.badge.text = risk.uppercase().replace("_", " ")
            h.badge.background.setTint(color)
        }
    }
}
