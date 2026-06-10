package com.pes.gamingdetector.activities

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
import com.pes.gamingdetector.api.CounselorMessage
import com.pes.gamingdetector.databinding.ActivityCounselorBinding
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.launch

class CounselorActivity : AppCompatActivity() {

    private lateinit var binding: ActivityCounselorBinding
    private lateinit var prefs: PrefsManager
    private val messages = mutableListOf<CounselorMessage>()
    private lateinit var adapter: MessageAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCounselorBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PrefsManager(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Mira"

        adapter = MessageAdapter()
        binding.rvMessages.layoutManager = LinearLayoutManager(this).apply {
            stackFromEnd = true
        }
        binding.rvMessages.adapter = adapter

        binding.btnSend.setOnClickListener { sendMessage() }

        loadHistory()
    }

    private fun loadHistory() {
        lifecycleScope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.counselorHistory(prefs.userId)
                if (resp.isSuccessful && resp.body()?.success == true) {
                    val history = resp.body()!!.messages
                    if (history.isEmpty()) {
                        // Show greeting if first time
                        messages.add(CounselorMessage(
                            "assistant",
                            "Hi! I'm Mira — your gaming wellness companion. How are you feeling today?",
                            null
                        ))
                    } else {
                        messages.addAll(history)
                    }
                    adapter.notifyDataSetChanged()
                    binding.rvMessages.scrollToPosition(messages.size - 1)
                }
            } catch (e: Exception) {
                Toast.makeText(this@CounselorActivity, "Couldn't load chat history", Toast.LENGTH_SHORT).show()
            }
        }
    }

    // Guards against double-taps on Send firing duplicate messages while a reply
    // is still in flight.
    private var awaitingReply = false

    private fun sendMessage() {
        val text = binding.etInput.text.toString().trim()
        if (text.isBlank() || awaitingReply) return
        awaitingReply = true
        binding.btnSend.isEnabled = false

        messages.add(CounselorMessage("user", text, null))
        adapter.notifyItemInserted(messages.size - 1)
        binding.etInput.text.clear()

        // Typing indicator bubble — replaced by the real reply (or removed on failure).
        messages.add(CounselorMessage("assistant", "…", null))
        adapter.notifyItemInserted(messages.size - 1)
        binding.rvMessages.scrollToPosition(messages.size - 1)

        lifecycleScope.launch {
            val typingIdx = messages.size - 1
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                val resp = api.counselorChat(mapOf(
                    "user_id" to prefs.userId,
                    "message" to text
                ))
                if (resp.isSuccessful && resp.body()?.success == true) {
                    messages[typingIdx] = CounselorMessage("assistant", resp.body()!!.reply, null)
                    adapter.notifyItemChanged(typingIdx)
                } else {
                    messages.removeAt(typingIdx)
                    adapter.notifyItemRemoved(typingIdx)
                    Toast.makeText(this@CounselorActivity, "Couldn't send message", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                messages.removeAt(typingIdx)
                adapter.notifyItemRemoved(typingIdx)
                Toast.makeText(this@CounselorActivity, "Couldn't send message", Toast.LENGTH_SHORT).show()
            } finally {
                awaitingReply = false
                binding.btnSend.isEnabled = true
                if (messages.isNotEmpty()) binding.rvMessages.scrollToPosition(messages.size - 1)
            }
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private inner class MessageAdapter : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

        override fun getItemViewType(position: Int): Int =
            if (messages[position].role == "user") TYPE_USER else TYPE_ASSISTANT

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
            val layout = if (viewType == TYPE_USER) R.layout.item_message_user
                         else R.layout.item_message_assistant
            val v = LayoutInflater.from(parent.context).inflate(layout, parent, false)
            return MessageVH(v)
        }

        override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
            (holder as MessageVH).tv.text = messages[position].content
        }

        override fun getItemCount() = messages.size

        private inner class MessageVH(v: View) : RecyclerView.ViewHolder(v) {
            val tv: TextView = v.findViewById(R.id.tvMessage)
        }

        private val TYPE_USER = 1
        private val TYPE_ASSISTANT = 2
    }
}
