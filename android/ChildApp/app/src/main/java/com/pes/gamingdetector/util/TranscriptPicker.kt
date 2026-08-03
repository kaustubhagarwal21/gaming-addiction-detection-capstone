package com.pes.gamingdetector.util

import org.json.JSONObject

/**
 * Chooses ONE transcript per audio segment when dual-language STT is enabled.
 *
 * Why a picker exists (measured, 2026-08-04, offline gTTS smoke tests):
 *  - English speech through the HINDI model is destroyed ("kill yourself you
 *    worthless trash" -> "व स्ट्रॉस", served score 0.077) — so Hindi-only is not
 *    an option.
 *  - Hindi/code-mixed speech through the ENGLISH model is destroyed the same way
 *    ("madarchod noob team में मत आना" -> "mother new team much") — so
 *    English-only misses spoken Hindi abuse.
 *  - Submitting BOTH transcripts would double-count toward the session streak
 *    alert and let the junk hypothesis raise false alerts ("good game" through
 *    the Hindi model reads "दूध गेम", which scores 0.787).
 * The recogniser that actually understood the audio reports higher average
 * per-word confidence, so the segment keeps exactly one line: the higher-confidence
 * non-blank hypothesis (ties prefer English, the primary deployment language).
 */
object TranscriptPicker {

    data class Hypothesis(val text: String, val avgConf: Double)

    /** Parse a Vosk final-result JSON (SetWords(true)) into text + mean word conf.
     *  Missing/empty word list falls back to confidence 0 so junk never wins ties. */
    fun parse(voskFinalResultJson: String): Hypothesis {
        return try {
            val o = JSONObject(voskFinalResultJson)
            val text = o.optString("text").trim()
            val words = o.optJSONArray("result")
            var sum = 0.0
            var n = 0
            if (words != null) {
                for (i in 0 until words.length()) {
                    sum += words.getJSONObject(i).optDouble("conf", 0.0)
                    n++
                }
            }
            Hypothesis(text, if (n > 0) sum / n else 0.0)
        } catch (_: Exception) {
            Hypothesis("", 0.0)
        }
    }

    /** The one line to submit for this segment, or null when neither model heard
     *  usable speech. English wins ties so behaviour is unchanged for the
     *  English-speaking majority when confidences are equal. */
    fun pick(english: Hypothesis, hindi: Hypothesis): String? {
        val enOk = english.text.isNotBlank()
        val hiOk = hindi.text.isNotBlank()
        return when {
            enOk && hiOk -> if (hindi.avgConf > english.avgConf) hindi.text else english.text
            enOk -> english.text
            hiOk -> hindi.text
            else -> null
        }
    }
}
