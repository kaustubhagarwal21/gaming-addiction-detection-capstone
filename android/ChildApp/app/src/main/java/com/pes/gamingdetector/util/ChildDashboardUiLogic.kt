package com.pes.gamingdetector.util

import com.pes.gamingdetector.api.ChildEnrichedResponse

/**
 * Pure mapping for the dashboard's optional cards.
 *
 * Returning a complete state (including hidden/blank defaults) makes every refresh
 * replace the previous render instead of only mutating fields that happen to be present.
 */
internal data class ChildDashboardOptionalState(
    val showStreak: Boolean = false,
    val selfAwarenessMessage: String = "",
    val currentStreakDays: Int = 0,
    val longestStreakDays: Int = 0,
    val streakBadge: String = "",
    val showLimit: Boolean = false,
    val dailyLimitHours: Double = 0.0,
    val usedTodayHours: Double = 0.0,
    val remainingHours: Double = 0.0,
    val limitExceeded: Boolean = false,
    val limitProgress: Int = 0,
)

internal object ChildDashboardUiLogic {
    fun optionalState(response: ChildEnrichedResponse?): ChildDashboardOptionalState {
        if (response?.success != true) return ChildDashboardOptionalState()

        val streak = response.streak
        val current = streak?.currentStreak?.coerceAtLeast(0) ?: 0
        val longest = streak?.longestStreak?.coerceAtLeast(0) ?: 0

        val limit = response.limitStatus?.takeIf {
            it.dailyLimitHours.isFinite() && it.dailyLimitHours > 0.0 &&
                it.usedTodayHours.isFinite() && it.usedTodayHours >= 0.0 &&
                it.remainingHours.isFinite()
        }
        val progress = limit?.let {
            ((it.usedTodayHours / it.dailyLimitHours) * 100.0)
                .toInt()
                .coerceIn(0, 100)
        } ?: 0

        return ChildDashboardOptionalState(
            showStreak = streak != null,
            selfAwarenessMessage = response.selfAwarenessMessage.orEmpty(),
            currentStreakDays = current,
            longestStreakDays = longest,
            streakBadge = if (streak == null) "" else badgeFor(current),
            showLimit = limit != null,
            dailyLimitHours = limit?.dailyLimitHours ?: 0.0,
            usedTodayHours = limit?.usedTodayHours ?: 0.0,
            remainingHours = limit?.remainingHours?.coerceAtLeast(0.0) ?: 0.0,
            limitExceeded = limit?.exceeded == true,
            limitProgress = progress,
        )
    }

    private fun badgeFor(currentStreak: Int): String = when {
        currentStreak >= 30 -> "🥇 Gold"
        currentStreak >= 14 -> "🥈 Silver"
        currentStreak >= 7 -> "🥉 Bronze"
        currentStreak >= 3 -> "⭐ Starter"
        else -> "🔒"
    }
}
