package com.pes.parentmonitor.util

import java.util.Locale
import kotlin.math.roundToInt

/**
 * One presentation contract for the risk summary shown across parent-facing screens.
 *
 * [category] is the stable machine value used for colours and recommendation rules;
 * [serverLabel] is the parent-friendly screening label returned by the dashboard API.
 */
object RiskPresentation {
    fun displayLabel(category: String?, serverLabel: String?): String {
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

    fun periodText(label: String?, sessions: Int?): String? {
        val cleanLabel = label?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        return if (sessions == null) {
            cleanLabel
        } else {
            "$cleanLabel · $sessions ${if (sessions == 1) "session" else "sessions"}"
        }
    }

    fun detailText(score: Double?, periodLabel: String?, sessions: Int?): String =
        listOfNotNull(
            "${scoreText(score)} risk score",
            periodText(periodLabel, sessions)
        ).joinToString(" · ")
}
