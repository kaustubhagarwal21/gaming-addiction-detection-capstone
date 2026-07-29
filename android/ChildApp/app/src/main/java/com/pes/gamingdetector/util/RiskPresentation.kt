package com.pes.gamingdetector.util

import java.util.Locale
import kotlin.math.roundToInt

/**
 * One presentation contract for risk results on every family-facing surface, in BOTH
 * apps: [category] is the stable machine key (colours, rules, storage); [serverLabel]
 * is the screening label the API sends. The UI never shows a child or parent a
 * clinical-sounding raw key.
 *
 * KEEP THE TWO COPIES IDENTICAL apart from the package line — CI diffs
 * ChildApp/.../RiskPresentation.kt against ParentApp/.../RiskPresentation.kt and
 * fails the build if they diverge (they did once; see the risk-consistency release).
 */
object RiskPresentation {
    private const val SEPARATOR = " · "
    private val KEY_SEPARATOR = Regex("[\\s-]+")

    private fun key(value: String): String =
        value.trim().lowercase(Locale.ROOT).replace(KEY_SEPARATOR, "_")

    private fun knownLabel(value: String?): String? = when (value?.takeIf { it.isNotBlank() }?.let(::key)) {
        "casual", "low_concern" -> "Low concern"
        "at_risk", "some_concern" -> "Some concern"
        "addicted", "high_concern" -> "High concern"
        else -> null
    }

    fun displayLabel(category: String?, serverLabel: String? = null): String {
        // A known machine category drives colours and recommendation rules, so it must
        // also drive the text. Letting a stale/conflicting serverLabel win could show
        // "Low concern" on an amber at_risk card. The server label remains the fallback
        // for legacy/future payloads whose category is absent or not yet recognised.
        knownLabel(category)?.let { return it }
        knownLabel(serverLabel)?.let { return it }
        val value = serverLabel?.trim()?.takeIf { it.isNotEmpty() }
            ?: category?.trim()?.takeIf { it.isNotEmpty() }
            ?: return "Unknown"
        return key(value).replace('_', ' ')
            .replaceFirstChar { it.titlecase(Locale.ROOT) }
    }

    private fun validScore(score: Double?): Double? =
        score?.takeIf { it.isFinite() && it in 0.0..1.0 }

    fun scoreText(score: Double?): String = validScore(score)?.let {
        "${(it * 100).roundToInt()}%"
    } ?: "—"

    fun riskScoreText(score: Double?): String = validScore(score)?.let {
        "${scoreText(it)} risk score"
    } ?: "Risk score unavailable"

    fun periodText(label: String?, sessions: Int?): String? {
        val cleanLabel = label?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        return if (sessions == null) {
            cleanLabel
        } else {
            "$cleanLabel$SEPARATOR$sessions ${if (sessions == 1) "session" else "sessions"}"
        }
    }

    fun detailText(score: Double?, periodLabel: String?, sessions: Int?): String =
        listOfNotNull(
            riskScoreText(score),
            periodText(periodLabel, sessions)
        ).joinToString(SEPARATOR)

    fun scopedRiskText(
        scope: String,
        category: String?,
        score: Double?,
        serverLabel: String? = null
    ): String {
        val parts = listOfNotNull(
            displayLabel(category, serverLabel),
            validScore(score)?.let { scoreText(it) }
        )
        return "$scope: ${parts.joinToString(SEPARATOR)}"
    }
}
