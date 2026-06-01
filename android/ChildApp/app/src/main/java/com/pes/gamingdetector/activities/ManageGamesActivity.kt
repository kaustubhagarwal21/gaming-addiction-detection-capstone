package com.pes.gamingdetector.activities

import android.content.Intent
import android.content.pm.ApplicationInfo
import android.graphics.drawable.Drawable
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.pes.gamingdetector.R
import com.pes.gamingdetector.databinding.ActivityManageGamesBinding
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Lets the parent manually mark an installed app as a game. This closes the one gap the
 * OS can't help with: a real game that reports a non-game category and isn't in the
 * curated list, so auto-detection would miss it. Stored on this device (force-include
 * set) — no server sync needed; the running monitor picks up changes on the next poll.
 *
 * Only shows user-installed launchable apps that aren't already detected as games, since
 * those are exactly the candidates a parent might need to add.
 */
class ManageGamesActivity : AppCompatActivity() {

    private lateinit var binding: ActivityManageGamesBinding
    private lateinit var prefs: PrefsManager
    private val included = HashSet<String>()   // force-include (not auto-detected)
    private val excluded = HashSet<String>()   // force-exclude (overrides auto-detection)

    private data class AppItem(val pkg: String, val label: String, val icon: Drawable?,
                               val isAuto: Boolean, var checked: Boolean)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityManageGamesBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Manage Games"

        included.addAll(prefs.forcedGamePackages)
        excluded.addAll(prefs.excludedGamePackages)
        binding.rvApps.layoutManager = LinearLayoutManager(this)
        loadApps()
    }

    private fun loadApps() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val items = withContext(Dispatchers.Default) { buildAppList() }
            binding.progressBar.visibility = View.GONE
            if (items.isEmpty()) {
                binding.tvEmpty.visibility = View.VISIBLE
            } else {
                binding.rvApps.adapter = AppAdapter(items)
            }
        }
    }

    private fun buildAppList(): List<AppItem> {
        val pm = packageManager
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val seen = HashSet<String>()
        val out = ArrayList<AppItem>()
        for (ri in pm.queryIntentActivities(launcher, 0)) {
            val ai = ri.activityInfo?.applicationInfo ?: continue
            val pkg = ai.packageName
            if (pkg == packageName || !seen.add(pkg)) continue
            // Show user-installed launchable apps (games are user-installed). Both
            // directions are offered: tick a non-game that's really a game, or untick a
            // (mis)detected game to stop monitoring it — so don't filter out auto-games.
            val pureSystem = (ai.flags and ApplicationInfo.FLAG_SYSTEM) != 0 &&
                             (ai.flags and ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) == 0
            if (pureSystem) continue
            val label  = try { pm.getApplicationLabel(ai).toString() } catch (_: Exception) { pkg }
            val icon   = try { pm.getApplicationIcon(ai) } catch (_: Exception) { null }
            val isAuto = GameDetector.isAutoDetectedGame(this, pkg)
            out.add(AppItem(pkg, label, icon, isAuto, GameDetector.isGame(this, pkg)))
        }
        out.sortBy { it.label.lowercase() }
        return out
    }

    private fun toggle(item: AppItem, checked: Boolean) {
        item.checked = checked
        // Store only deviations from auto-detection so the sets stay minimal:
        //  checked   → never exclude; force-include only if the OS wouldn't detect it.
        //  unchecked → never include; force-exclude only if the OS would detect it.
        if (checked) {
            excluded.remove(item.pkg)
            if (item.isAuto) included.remove(item.pkg) else included.add(item.pkg)
        } else {
            included.remove(item.pkg)
            if (item.isAuto) excluded.add(item.pkg) else excluded.remove(item.pkg)
        }
        prefs.forcedGamePackages   = included
        prefs.excludedGamePackages = excluded
        GameDetector.invalidate()   // running monitor picks it up on the next poll
    }

    private inner class AppAdapter(val items: List<AppItem>) :
        RecyclerView.Adapter<AppAdapter.VH>() {

        inner class VH(v: View) : RecyclerView.ViewHolder(v) {
            val icon: ImageView = v.findViewById(R.id.ivIcon)
            val label: TextView = v.findViewById(R.id.tvLabel)
            val cb: CheckBox = v.findViewById(R.id.cbGame)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
            VH(LayoutInflater.from(parent.context).inflate(R.layout.item_app_toggle, parent, false))

        override fun getItemCount() = items.size

        override fun onBindViewHolder(h: VH, position: Int) {
            val item = items[position]
            h.label.text = item.label
            h.icon.setImageDrawable(item.icon)
            h.cb.isChecked = item.checked
            // The checkbox itself isn't clickable (clickable=false in the row); tapping
            // anywhere on the row flips it, which is the larger, friendlier touch target.
            h.itemView.setOnClickListener {
                val newState = !item.checked
                h.cb.isChecked = newState
                toggle(item, newState)
            }
        }
    }

    override fun onSupportNavigateUp(): Boolean { finish(); return true }
}
