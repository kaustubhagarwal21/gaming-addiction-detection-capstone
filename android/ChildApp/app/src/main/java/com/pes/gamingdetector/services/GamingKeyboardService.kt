package com.pes.gamingdetector.services

import android.inputmethodservice.InputMethodService
import android.inputmethodservice.Keyboard
import android.inputmethodservice.KeyboardView
import android.view.View
import android.view.inputmethod.EditorInfo
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.ForegroundResolver
import com.pes.gamingdetector.util.GameDetector
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Custom on-screen keyboard (IME).
 *
 * Why this exists: canvas/engine games like Roblox render their chat box inside their own
 * GL surface, so the AccessibilityService can't read the typed text, and most keyboards
 * (Gboard) don't emit per-key accessibility events for the keystroke fallback to work.
 *
 * Because every character the child types flows through the keyboard *before* it reaches
 * the app, owning the keyboard is the one fool-proof, OCR-free way to capture typed
 * in-game chat. It also captures ONLY the child's own keystrokes — never other players'
 * messages, HUD, or game text — so there's nothing to disambiguate.
 *
 * Privacy: a typed line is uploaded only when the foreground app is a monitored game and
 * a session is active (same gating as the accessibility path). Everywhere else — search,
 * passwords, banking — the keyboard works normally but captures nothing.
 */
class GamingKeyboardService : InputMethodService(), KeyboardView.OnKeyboardActionListener {

    private lateinit var keyboardView: KeyboardView
    private lateinit var qwerty: Keyboard
    private lateinit var symbols: Keyboard
    private lateinit var prefs: PrefsManager

    private var caps = false
    private val buffer = StringBuilder()
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreateInputView(): View {
        prefs = PrefsManager(this)
        qwerty = Keyboard(this, R.xml.qwerty)
        symbols = Keyboard(this, R.xml.symbols)
        keyboardView = layoutInflater.inflate(R.layout.keyboard_view, null) as KeyboardView
        keyboardView.keyboard = qwerty
        keyboardView.isPreviewEnabled = false      // no per-key popup bubbles
        keyboardView.setOnKeyboardActionListener(this)
        return keyboardView
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        buffer.setLength(0)
        caps = false
        if (::keyboardView.isInitialized) {
            keyboardView.keyboard = qwerty
            qwerty.isShifted = false
            keyboardView.invalidateAllKeys()
        }
    }

    override fun onKey(primaryCode: Int, keyCodes: IntArray?) {
        val ic = currentInputConnection ?: return
        when (primaryCode) {
            Keyboard.KEYCODE_DELETE -> {
                ic.deleteSurroundingText(1, 0)
                if (buffer.isNotEmpty()) buffer.deleteCharAt(buffer.length - 1)
            }
            Keyboard.KEYCODE_SHIFT -> {
                caps = !caps
                qwerty.isShifted = caps
                keyboardView.invalidateAllKeys()
            }
            Keyboard.KEYCODE_MODE_CHANGE -> {
                keyboardView.keyboard = if (keyboardView.keyboard === qwerty) symbols else qwerty
                keyboardView.invalidateAllKeys()
            }
            10 -> {                                 // enter / send
                flushCapture()
                val action = currentInputEditorInfo?.imeOptions?.and(EditorInfo.IME_MASK_ACTION)
                    ?: EditorInfo.IME_ACTION_UNSPECIFIED
                if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED) {
                    sendDefaultEditorAction(true)   // "Send" on chat fields
                } else {
                    ic.commitText("\n", 1)
                }
            }
            32 -> {                                 // space
                ic.commitText(" ", 1)
                buffer.append(' ')
            }
            else -> {
                var code = primaryCode
                if (caps && Character.isLetter(code)) code = Character.toUpperCase(code)
                val ch = code.toChar()
                ic.commitText(ch.toString(), 1)
                buffer.append(ch)
                if (caps) {                         // one-shot shift
                    caps = false
                    qwerty.isShifted = false
                    keyboardView.invalidateAllKeys()
                }
            }
        }
    }

    /** Field lost focus / input ended — flush whatever was typed so far. */
    override fun onFinishInput() {
        flushCapture()
        super.onFinishInput()
    }

    /**
     * Upload the buffered sentence — but ONLY if the child is genuinely in a monitored
     * game with an active session. Otherwise discard it (never leaves the device).
     */
    private fun flushCapture() {
        val text = buffer.toString().trim()
        buffer.setLength(0)
        if (text.length < 3) return
        val sid = prefs.activeSessionId
        if (sid == -1) return
        if (!GameDetector.isGame(this, ForegroundResolver.current(this))) return
        scope.launch {
            try {
                ApiClient.getInstance(prefs.serverUrl)
                    .uploadChat(sid, mapOf("message" to text, "source" to "keyboard"))
            } catch (_: Exception) { /* best-effort; offline lines are simply skipped */ }
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    // ── unused OnKeyboardActionListener callbacks ─────────────────────────
    override fun onPress(primaryCode: Int) {}
    override fun onRelease(primaryCode: Int) {}
    override fun onText(text: CharSequence?) {}
    override fun swipeLeft() {}
    override fun swipeRight() {}
    override fun swipeDown() {}
    override fun swipeUp() {}
}
