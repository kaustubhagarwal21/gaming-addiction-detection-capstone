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
import com.pes.gamingdetector.util.RiskPresentation
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Locale

class SessionHistoryActivity : AuthenticatedActivity() {
    private lateinit var binding: ActivitySessionHistoryBinding
    private lateinit var prefs: PrefsManager
    private var loadJob: Job? = null
    private var loadGeneration = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!ensureAuthenticatedOnCreate()) return
        binding = ActivitySessionHistoryBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Session History"

        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.swipeRefresh.setOnRefreshListener { loadHistory() }
    }

    override fun onAuthenticatedResume() {
        loadHistory()
    }

    private fun loadHistory() {
        if (loadJob?.isActive == true) return
        val generation = ++loadGeneration
        binding.progressBar.visibility = View.VISIBLE
        loadJob = lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.getSessions(prefs.userId)
                if (generation == loadGeneration && resp.isSuccessful) {
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
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation == loadGeneration) {
                    Toast.makeText(
                        this@SessionHistoryActivity,
                        "Load failed: ${e.message}",
                        Toast.LENGTH_SHORT,
                    ).show()
                }
            } finally {
                if (generation == loadGeneration) {
                    binding.progressBar.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
                    loadJob = null
                }
            }
        }
    }

    override fun onStop() {
        ++loadGeneration
        loadJob?.cancel()
        loadJob = null
        if (::binding.isInitialized) {
            binding.progressBar.visibility = View.GONE
            binding.swipeRefresh.isRefreshing = false
        }
        super.onStop()
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

            // An unfinished/unscored session is unknown, not automatically low concern.
            val risk  = s.riskCategory?.lowercase() ?: "unknown"
            val color = when (risk) {
                "addicted" -> getColor(R.color.risk_high)
                "at_risk"  -> getColor(R.color.risk_medium)
                "casual"   -> getColor(R.color.risk_low)
                else       -> Color.GRAY
            }
            h.dot.background.setTint(color)
            h.badge.text = RiskPresentation.displayLabel(risk)
            h.badge.background.setTint(color)
        }
    }
}
