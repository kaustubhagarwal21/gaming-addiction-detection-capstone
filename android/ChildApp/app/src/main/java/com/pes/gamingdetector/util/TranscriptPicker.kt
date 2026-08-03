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

    /** Confidence gap below which a segment is treated as GENUINELY code-mixed
     *  (both models confidently heard real, different words) rather than one model
     *  producing junk. Measured offline: same-language junk sat >=0.30 below the
     *  correct model's confidence, while a real bilingual window kept both models
     *  close — so a small gap plus low text overlap is the honest "keep both" case. */
    private const val MIXED_CONF_GAP = 0.15

    /** Segment transcript(s) to submit. Usually one line (see [pick]); returns BOTH
     *  when the window genuinely contains both languages — both models confident,
     *  close in confidence, and their texts barely overlap (so we are not
     *  double-counting the same utterance heard two ways). This closes the
     *  weak spot where a single segment holding one Hindi and one English sentence
     *  otherwise loses half its content. Each returned line is scored independently
     *  server-side; the streak alert already de-duplicates by content. */
    fun pickAll(english: Hypothesis, hindi: Hypothesis): List<String> {
        val enOk = english.text.isNotBlank()
        val hiOk = hindi.text.isNotBlank()
        if (!enOk || !hiOk) return listOfNotNull(pick(english, hindi))
        val bothConfident = english.avgConf >= 0.5 && hindi.avgConf >= 0.5
        val closeConf = kotlin.math.abs(english.avgConf - hindi.avgConf) <= MIXED_CONF_GAP
        if (bothConfident && closeConf && tokenOverlap(english.text, hindi.text) < 0.5) {
            return listOf(english.text, hindi.text)
        }
        return listOf(pick(english, hindi)!!)
    }

    /** Jaccard overlap of lowercased word sets — high overlap means the two models
     *  transcribed the SAME utterance (keep one), low overlap means different
     *  content (a real mixed window). */
    private fun tokenOverlap(a: String, b: String): Double {
        val sa = a.lowercase().split(Regex("\\s+")).filter { it.isNotBlank() }.toSet()
        val sb = b.lowercase().split(Regex("\\s+")).filter { it.isNotBlank() }.toSet()
        if (sa.isEmpty() || sb.isEmpty()) return 0.0
        val inter = sa.intersect(sb).size.toDouble()
        return inter / (sa.size + sb.size - inter)
    }
}
