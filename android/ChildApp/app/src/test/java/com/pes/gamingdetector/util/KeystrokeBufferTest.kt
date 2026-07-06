package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Sentence reconstruction from IME key labels. The regression block pins the
 * word-vs-key classification bug: suggestion-bar words that merely CONTAIN a key
 * token ("center", "sending", "deleted") were misread as the Enter/Delete key,
 * flushing the sentence early and dropping the word.
 */
class KeystrokeBufferTest {

    private fun buffer(out: MutableList<String>) = KeystrokeBuffer { out.add(it) }

    @Test
    fun `letters assemble and enter key flushes the sentence`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        "gg wp".forEach { kb.handleKey(if (it == ' ') "space" else it.toString()) }
        kb.handleKey("Send")
        assertEquals(listOf("gg wp"), out)
    }

    @Test
    fun `shift is one-shot uppercase`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        kb.handleKey("shift"); kb.handleKey("h"); kb.handleKey("e"); kb.handleKey("y")
        kb.flush()
        assertEquals(listOf("Hey"), out)
    }

    @Test
    fun `backspace key removes the last character`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        listOf("n", "o", "b", "x", "delete", "delete", "o", "b").forEach { kb.handleKey(it) }
        kb.flush()
        assertEquals(listOf("noob"), out)
    }

    @Test
    fun `suggestion-bar word taps join the sentence`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        kb.handleKey("nice"); kb.handleKey("shot")
        kb.flush()
        assertEquals(listOf("nice shot"), out)
    }

    @Test
    fun `too-short buffers are dropped on flush, not submitted`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        kb.handleKey("g"); kb.handleKey("g")
        kb.flush()
        assertTrue(out.isEmpty())
    }

    // ── regression: words containing key tokens are WORDS, not keys ──────────

    @Test
    fun `words embedding enter-send-delete tokens are captured, not treated as keys`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        // "center" contains "enter", "sending" contains "send", "deleted" contains
        // "delete" — each used to flush (or backspace) instead of joining the sentence.
        kb.handleKey("meet"); kb.handleKey("center"); kb.handleKey("before")
        kb.handleKey("sending"); kb.handleKey("deleted"); kb.handleKey("items")
        kb.flush()
        assertEquals(listOf("meet center before sending deleted items"), out)
    }

    @Test
    fun `multi-word key labels still count as keys`() {
        val out = mutableListOf<String>()
        val kb = buffer(out)
        kb.handleKey("hello"); kb.handleKey("there")
        kb.handleKey("Send message")   // Gboard-style action label → flush
        assertEquals(listOf("hello there"), out)
        "okayy".forEach { kb.handleKey(it.toString()) }
        kb.handleKey("Delete key")     // action label → backspace, not the word "delete"
        kb.flush()
        assertEquals(listOf("hello there", "okay"), out)
    }
}
