package com.pes.gamingdetector.util

/** Pure transition logic behind the monitor's capture-permission self-heal prompt. */
object CaptureHealthLogic {
    enum class Loss { KEYBOARD, ACCESSIBILITY }

    /** Bits are accessibility then selected keyboard (for example, "11" = both on).
     *  The keyboard is reported first when both disappear because opening HomeActivity
     *  still walks the user through accessibility before the keyboard steps. */
    fun loss(previous: String?, current: String): Loss? {
        if (previous?.length != 2 || current.length != 2) return null
        return when {
            previous[1] == '1' && current[1] == '0' -> Loss.KEYBOARD
            previous[0] == '1' && current[0] == '0' -> Loss.ACCESSIBILITY
            else -> null
        }
    }
}
