package com.pes.parentmonitor.util

import com.pes.parentmonitor.api.Alert

/**
 * The pure decision logic of AlertPollingService — which alerts are new, which one to
 * surface, and when a risk change deserves a (re-)notification. No Android types, so
 * it runs under plain-JVM unit tests; the service owns polling, prefs, and the
 * notification plumbing.
 */
object AlertTriage {
    /** One risk-change notification per child+level per window is plenty. */
    const val RISK_RENOTIFY_MS = 30 * 60 * 1000L

    fun severityRank(s: String): Int = when (s.lowercase()) {
        "high"   -> 3
        "medium" -> 2
        "low"    -> 1
        else     -> 0
    }

    /** Unread alerts newer than the per-child high-water mark, oldest first. Alert ids
     *  are globally unique, so the mark must be per child — a single shared mark
     *  suppressed a sibling's older-id alerts after viewing another child. */
    fun newAlertsSince(alerts: List<Alert>?, lastNotifiedId: Int): List<Alert> =
        alerts?.filter { !it.read && it.id > lastNotifiedId }?.sortedBy { it.id } ?: emptyList()

    /** The single alert worth one notification: highest severity wins. */
    fun worstOf(alerts: List<Alert>): Alert? = alerts.maxByOrNull { severityRank(it.severity) }

    /** Only elevated levels notify; a drop back to casual is visible in the app. */
    fun isNotifyWorthyRisk(risk: String): Boolean =
        risk.lowercase() in listOf("at_risk", "addicted")

    /**
     * Parent verdicts are useful only for alerts that contain a model/heuristic
     * assessment. Include aggregate streak alerts and late risk revisions as well as
     * their original one-event forms; operational events (login, offline, permission,
     * tamper, session start) are facts and must not ask "Was this accurate?".
     */
    fun isFeedbackEligible(type: String): Boolean =
        type.lowercase() in setOf(
            "risk",
            "risk_revision",
            "toxicity",
            "toxicity_streak",
        )

    /** Consecutive sessions either side of a band cut-off flip the level back and
     *  forth; the cooldown stops that turning into notification spam. */
    fun riskCooldownPassed(lastNotifiedAt: Long, now: Long): Boolean =
        now - lastNotifiedAt > RISK_RENOTIFY_MS
}
