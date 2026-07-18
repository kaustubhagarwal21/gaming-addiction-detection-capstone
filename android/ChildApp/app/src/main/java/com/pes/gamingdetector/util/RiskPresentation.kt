package com.pes.gamingdetector.util

import java.util.Locale
import kotlin.math.roundToInt

/**
 * Family-facing presentation rules for aggregate and per-session risk results.
 *
 * Category keys remain stable for API/storage logic, while every child-facing surface
 * uses the same non-clinical screening labels as the parent app.
 */
object RiskPresentation {
    private const val SEPARATOR = " \u00B7 "

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

    fun scoreText(score: Double): String =
        "${(score * 100).roundToInt()}%"

    fun riskScoreText(score: Double): String =
        "${scoreText(score)} risk score"

    fun periodText(label: String?, sessions: Int?): String? {
        val cleanLabel = label?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        return if (sessions == null) {
            cleanLabel
        } else {
            "$cleanLabel$SEPARATOR$sessions ${if (sessions == 1) "session" else "sessions"}"
        }
    }

    fun scopedRiskText(
        scope: String,
        category: String?,
        score: Double?,
        serverLabel: String? = null
    ): String {
        val parts = listOfNotNull(
            displayLabel(category, serverLabel),
            score?.let(::scoreText)
        )
        return "$scope: ${parts.joinToString(SEPARATOR)}"
    }
}
