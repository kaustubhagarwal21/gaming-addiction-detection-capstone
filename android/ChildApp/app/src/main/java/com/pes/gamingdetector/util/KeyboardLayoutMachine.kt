package com.pes.gamingdetector.util

/**
 * Pure state machine for the Wellbeing Keyboard's four layouts. Extracted from
 * GamingKeyboardService so the switching logic is JVM-testable — the keyboard is
 * the most privacy-sensitive surface in the app, and a wrong transition (e.g.
 * getting stuck on a Devanagari page with no way back) is exactly the kind of
 * defect that otherwise only shows up on a device. The service maps each
 * [Layout] to its android.inputmethodservice.Keyboard object; this class owns
 * only WHICH layout is active.
 *
 * Deliberate behaviour notes, mirrored from the shipped service:
 *  - MODE_CHANGE (?123) from any non-QWERTY layout returns to QWERTY (symbols is
 *    reachable only from QWERTY, matching the layout XMLs, which only place the
 *    ?123 key there and on the symbols page itself).
 *  - LANG_TOGGLE cycles QWERTY/SYMBOLS/VOWELS -> CONSONANTS, and CONSONANTS ->
 *    VOWELS (the same physical key reads "हिं" on QWERTY and "अआ" on the
 *    consonant page).
 *  - Every new input field starts at QWERTY (see [reset]) so a child is never
 *    greeted by a page they didn't choose.
 */
object KeyboardLayoutMachine {

    enum class Layout { QWERTY, SYMBOLS, DEVA_CONSONANTS, DEVA_VOWELS }

    // Key codes shared with the layout XMLs. Android's own
    // Keyboard.KEYCODE_MODE_CHANGE is -2; redefined here so this class has no
    // Android dependency and stays plain-JVM testable.
    const val KEY_MODE_CHANGE = -2
    const val KEY_TO_QWERTY = -100
    const val KEY_LANG_TOGGLE = -101
    const val KEY_TO_CONSONANTS = -102

    /** Layout every new input field starts on. */
    fun reset(): Layout = Layout.QWERTY

    /** The layout after [keyCode] is pressed while [current] is showing.
     *  Non-switching keys (letters, space, delete, shift, enter) return
     *  [current] unchanged. */
    fun next(current: Layout, keyCode: Int): Layout = when (keyCode) {
        KEY_MODE_CHANGE -> if (current == Layout.QWERTY) Layout.SYMBOLS else Layout.QWERTY
        KEY_LANG_TOGGLE -> if (current == Layout.DEVA_CONSONANTS) Layout.DEVA_VOWELS
                           else Layout.DEVA_CONSONANTS
        KEY_TO_CONSONANTS -> Layout.DEVA_CONSONANTS
        KEY_TO_QWERTY -> Layout.QWERTY
        else -> current
    }

    /** True when [layout] commits Devanagari characters — used by the service to
     *  skip the Latin-only caps handling on Hindi pages (Devanagari has no case). */
    fun isDevanagari(layout: Layout): Boolean =
        layout == Layout.DEVA_CONSONANTS || layout == Layout.DEVA_VOWELS
}
