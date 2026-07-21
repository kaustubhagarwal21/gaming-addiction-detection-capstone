package com.pes.parentmonitor.util

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

    fun displayLabel(category: String?, serverLabel: String? = null): String {
        val value = serverLabel?.trim()?.takeIf { it.isNotEmpty() }
            ?: category?.trim()?.takeIf { it.isNotEmpty() }
            ?: return "Unknown"
        val key = value.lowercase(Locale.ROOT)
            .replace('-', '_')
            .replace(' ', '_')
        return when (key) {
            "casual", "low_concern" -> "Low concern"
            "at_risk", "some_concern" -> "Some concern"
            "addicted", "high_concern" -> "High concern"
            else -> key.replace('_', ' ')
                .replaceFirstChar { it.titlecase(Locale.ROOT) }
        }
    }

    fun scoreText(score: Double?): String =
        "${((score ?: 0.0) * 100).roundToInt()}%"

    fun riskScoreText(score: Double?): String =
        "${scoreText(score)} risk score"

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
            score?.let { scoreText(it) }
        )
        return "$scope: ${parts.joinToString(SEPARATOR)}"
    }
}
