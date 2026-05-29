package com.pes.gamingdetector.services

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.ForegroundResolver
import com.pes.gamingdetector.util.ForegroundTracker
import com.pes.gamingdetector.util.KeystrokeBuffer
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class ChatAccessibilityService : AccessibilityService() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var lastText: String = ""
    private var lastTextChangeAt: Long = 0L
    private val EDIT_IDLE_FLUSH_MS = 4_000L  // submit a finished message after this idle

    // ── IME-keystroke capture state ──────────────────────────────────────
    private val keystrokeBuffer = KeystrokeBuffer { sentence ->
        val prefs = PrefsManager(this)
        submitChat(prefs, sentence, source = "ime_keystroke")
    }
    private val idleHandler = Handler(Looper.getMainLooper())
    private val idleFlusher = object : Runnable {
        override fun run() {
            keystrokeBuffer.flushIfIdle()
            // EditText idle flush: many games (Roblox) never fire an empty TEXT_CHANGED
            // or a Send click, so the final typed message has no "sent" signal. If the
            // field has sat unchanged for a few seconds, treat it as a completed message.
            if (lastText.length >= 3 &&
                System.currentTimeMillis() - lastTextChangeAt > EDIT_IDLE_FLUSH_MS
            ) {
                val prefs = PrefsManager(this@ChatAccessibilityService)
                if (prefs.hasActiveSession()) submitChat(prefs, lastText, source = "keyboard")
                lastText = ""
            }
            idleHandler.postDelayed(this, 1_000L)
        }
    }

    // Known OS-keyboard packages. Tap events from these are the keystrokes we
    // want to assemble into typed sentences. Add new IMEs here as needed.
    private val imePackages = setOf(
        "com.google.android.inputmethod.latin",     // Gboard
        "com.google.android.inputmethod.pinyin",
        "com.samsung.android.honeyboard",           // Samsung
        "com.touchtype.swiftkey",                   // SwiftKey
        "com.android.inputmethod.latin",            // AOSP keyboard
        "com.android.inputmethod.pinyin",
    )

    override fun onServiceConnected() {
        serviceInfo = AccessibilityServiceInfo().apply {
            eventTypes = AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED or
                    AccessibilityEvent.TYPE_VIEW_CLICKED or
                    AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
            notificationTimeout = 100
        }
        idleHandler.postDelayed(idleFlusher, 1_000L)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return

        // Window state changes feed the foreground tracker, regardless of session.
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            ForegroundTracker.update(event.packageName?.toString())
            return
        }

        val prefs = PrefsManager(this)
        if (!prefs.hasActiveSession()) return

        val srcPkg = event.packageName?.toString()

        // ── IME keystroke capture ────────────────────────────────────────
        // The on-screen keyboard is itself an Android app — every key tap fires
        // a TYPE_VIEW_CLICKED with the key's contentDescription. Only capture
        // when the active foreground app is a known game, so passwords/searches
        // in other apps are never logged.
        if (event.eventType == AccessibilityEvent.TYPE_VIEW_CLICKED && srcPkg in imePackages) {
            // Reliable foreground check (UsageStats-backed, cached) so keystrokes are
            // captured while genuinely in a game and never while in another app.
            val foreground = ForegroundResolver.current(this)
            if (foreground in Constants.KNOWN_GAMING_PACKAGES) {
                val label = event.contentDescription?.toString()
                    ?: event.text.joinToString("").takeIf { it.isNotEmpty() }
                keystrokeBuffer.handleKey(label)
            }
            return
        }

        when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> {
                // A real EditText is handling this input, so it's authoritative — drop
                // any parallel IME-keystroke accumulation to avoid submitting the same
                // message twice (once as "keyboard", once as "ime_keystroke"). The IME
                // path is only meant for canvas games that emit no TEXT_CHANGED events.
                keystrokeBuffer.clear()
                lastTextChangeAt = System.currentTimeMillis()
                val newText = event.text.joinToString(" ").trim()
                when {
                    newText.isEmpty() -> {
                        // Field cleared (WhatsApp/SMS/Discord on send) — submit message.
                        if (lastText.length >= 3) submitChat(prefs, lastText, source = "keyboard")
                        lastText = ""
                    }
                    // Field dropped by more than one character at once → the previous
                    // message was sent/cleared and a new one is starting. Within a single
                    // message the field only ever changes by ±1 char per event (typing a
                    // char, or one backspace), so a bigger drop is a message boundary.
                    // This works even when consecutive messages share a prefix (a prefix
                    // check wrongly treats "message two" → "m" as backspacing).
                    newText.length < lastText.length - 1 -> {
                        if (lastText.length >= 3) submitChat(prefs, lastText, source = "keyboard")
                        lastText = newText
                    }
                    // Otherwise still composing the same message (added chars / 1 backspace).
                    else -> lastText = newText
                }
            }
            AccessibilityEvent.TYPE_VIEW_CLICKED -> {
                // Non-IME click — user is interacting outside the keyboard.
                // Flush any in-progress IME sentence, then handle the EditText
                // "send button tapped" heuristic.
                keystrokeBuffer.flush()
                val msg = lastText.trim()
                if (msg.length >= 3) {
                    submitChat(prefs, msg, source = "keyboard")
                    lastText = ""
                }
            }
        }
    }

    private fun submitChat(prefs: PrefsManager, message: String, source: String) {
        val sessionId = prefs.activeSessionId
        if (sessionId == -1) return
        scope.launch {
            try {
                val api = ApiClient.getInstance(prefs.serverUrl)
                api.uploadChat(sessionId, mapOf("message" to message, "source" to source))
            } catch (_: Exception) {}
        }
    }

    override fun onInterrupt() {
        keystrokeBuffer.clear()
    }

    override fun onDestroy() {
        idleHandler.removeCallbacks(idleFlusher)
        keystrokeBuffer.clear()
        super.onDestroy()
    }
}
