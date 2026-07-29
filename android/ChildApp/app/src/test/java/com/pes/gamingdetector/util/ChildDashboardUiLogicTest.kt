package com.pes.gamingdetector.util

import com.pes.gamingdetector.api.ChildEnrichedResponse
import com.pes.gamingdetector.api.LimitStatus
import com.pes.gamingdetector.api.StreakInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChildDashboardUiLogicTest {
    @Test
    fun `missing or unsuccessful enriched data resets every optional section`() {
        for (response in listOf(
            null,
            ChildEnrichedResponse(
                success = false,
                childName = null,
                streak = StreakInfo(8, 12, 20),
                limitStatus = LimitStatus(2.0, 1.0, 1.0, false),
                playedTodayHours = null,
                dailyGoalHours = null,
                goalIsParentSet = null,
                selfAwarenessMessage = "stale",
            ),
        )) {
            val state = ChildDashboardUiLogic.optionalState(response)
            assertFalse(state.showStreak)
            assertFalse(state.showLimit)
            assertEquals("", state.selfAwarenessMessage)
            assertEquals("", state.streakBadge)
            assertEquals(0, state.limitProgress)
        }
    }

    @Test
    fun `present optional data fully replaces the rendered state`() {
        val state = ChildDashboardUiLogic.optionalState(
            ChildEnrichedResponse(
                success = true,
                childName = "Child",
                streak = StreakInfo(14, 21, 40),
                limitStatus = LimitStatus(2.0, 0.75, 1.25, false),
                playedTodayHours = 0.75,
                dailyGoalHours = 2.0,
                goalIsParentSet = true,
                selfAwarenessMessage = "Steady progress",
            )
        )

        assertTrue(state.showStreak)
        assertEquals("Steady progress", state.selfAwarenessMessage)
        assertEquals(14, state.currentStreakDays)
        assertEquals(21, state.longestStreakDays)
        assertEquals("🥈 Silver", state.streakBadge)
        assertTrue(state.showLimit)
        assertEquals(37, state.limitProgress)
    }

    @Test
    fun `invalid limit payload is hidden instead of rendering non-finite progress`() {
        val state = ChildDashboardUiLogic.optionalState(
            ChildEnrichedResponse(
                success = true,
                childName = null,
                streak = null,
                limitStatus = LimitStatus(0.0, Double.NaN, Double.NaN, false),
                playedTodayHours = null,
                dailyGoalHours = null,
                goalIsParentSet = null,
                selfAwarenessMessage = null,
            )
        )

        assertFalse(state.showLimit)
        assertEquals(0, state.limitProgress)
        assertEquals(0.0, state.dailyLimitHours, 0.0)
    }
}
