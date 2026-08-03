package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Dual-language STT segment picker. The measured motivations these tests pin:
 * each Vosk model destroys the other language (EN model: "madarchod noob" ->
 * "mother new"; HI model: "kill yourself" -> "व स्ट्रॉस"), and submitting both
 * hypotheses per segment would double-count toward the streak alert and let the
 * junk hypothesis ("good game" -> "दूध गेम", scoring 0.787) raise false alerts —
 * so exactly ONE line may survive per segment, chosen by word confidence.
 */
class TranscriptPickerTest {

    private fun h(text: String, conf: Double) = TranscriptPicker.Hypothesis(text, conf)

    @Test
    fun `hindi speech - hindi model wins on confidence`() {
        assertEquals("मादरचोद टीम में मत आना",
            TranscriptPicker.pick(h("mother new team much", 0.42),
                                  h("मादरचोद टीम में मत आना", 0.86)))
    }

    @Test
    fun `english speech - english model wins on confidence`() {
        assertEquals("kill yourself you worthless trash",
            TranscriptPicker.pick(h("kill yourself you worthless trash", 0.91),
                                  h("व स्ट्रॉस", 0.38)))
    }

    @Test
    fun `equal confidence prefers english so existing behaviour is unchanged`() {
        assertEquals("good game", TranscriptPicker.pick(h("good game", 0.7), h("दूध गेम", 0.7)))
    }

    @Test
    fun `blank english falls through to hindi`() {
        assertEquals("चूतिया", TranscriptPicker.pick(h("", 0.0), h("चूतिया", 0.6)))
    }

    @Test
    fun `both blank yields nothing to submit`() {
        assertNull(TranscriptPicker.pick(h("", 0.0), h("  ", 0.9)))
    }

    @Test
    fun `parse reads text and mean word confidence from vosk json`() {
        val json = """{"result":[{"conf":0.9,"word":"gg"},{"conf":0.7,"word":"wp"}],"text":"gg wp"}"""
        val hyp = TranscriptPicker.parse(json)
        assertEquals("gg wp", hyp.text)
        assertEquals(0.8, hyp.avgConf, 1e-9)
    }

    @Test
    fun `parse without word list gets zero confidence so junk never wins ties`() {
        val hyp = TranscriptPicker.parse("""{"text":"दूध गेम"}""")
        assertEquals("दूध गेम", hyp.text)
        assertEquals(0.0, hyp.avgConf, 1e-9)
    }

    @Test
    fun `parse survives malformed json`() {
        val hyp = TranscriptPicker.parse("not json at all")
        assertEquals("", hyp.text)
        assertEquals(0.0, hyp.avgConf, 1e-9)
    }

    // ── pickAll: the mixed-window mitigation ──────────────────────────────

    @Test
    fun `genuinely mixed window keeps both transcripts`() {
        // Both models confident, close confidence, no shared words: a real
        // bilingual segment (one English + one Hindi sentence in one window).
        val out = TranscriptPicker.pickAll(h("push mid now team", 0.82),
                                           h("मादरचोद मत आना", 0.78))
        assertEquals(listOf("push mid now team", "मादरचोद मत आना"), out)
    }

    @Test
    fun `junk hypothesis with big confidence gap still yields one line`() {
        // English speech, Hindi model junk 0.30+ below: single line, no false alert.
        val out = TranscriptPicker.pickAll(h("good game well played", 0.88),
                                           h("दूध गेम वेल", 0.41))
        assertEquals(listOf("good game well played"), out)
    }

    @Test
    fun `same utterance heard two ways keeps only the winner`() {
        // High token overlap = one utterance transcribed twice — never two lines.
        val out = TranscriptPicker.pickAll(h("uninstall kar de bro", 0.80),
                                           h("uninstall kar de ब्रो", 0.75))
        assertEquals(listOf("uninstall kar de bro"), out)
    }

    @Test
    fun `low confidence pair falls back to single pick`() {
        val out = TranscriptPicker.pickAll(h("mumble", 0.30), h("बड़बड़", 0.35))
        assertEquals(1, out.size)
    }
}
