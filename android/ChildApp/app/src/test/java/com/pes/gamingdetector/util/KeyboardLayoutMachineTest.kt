package com.pes.gamingdetector.util

import com.pes.gamingdetector.util.KeyboardLayoutMachine.Layout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Full transition table of the Wellbeing Keyboard's layout state machine. Every
 * (state, switching-key) pair is asserted, because the failure mode that matters
 * — a page with no route back to QWERTY — is a stuck keyboard for a child
 * mid-game, and that must be impossible by construction.
 */
class KeyboardLayoutMachineTest {

    private val m = KeyboardLayoutMachine

    @Test
    fun `every field starts on qwerty`() {
        assertEquals(Layout.QWERTY, m.reset())
    }

    @Test
    fun `mode change toggles qwerty and symbols`() {
        assertEquals(Layout.SYMBOLS, m.next(Layout.QWERTY, m.KEY_MODE_CHANGE))
        assertEquals(Layout.QWERTY, m.next(Layout.SYMBOLS, m.KEY_MODE_CHANGE))
    }

    @Test
    fun `mode change from either devanagari page returns to qwerty`() {
        assertEquals(Layout.QWERTY, m.next(Layout.DEVA_CONSONANTS, m.KEY_MODE_CHANGE))
        assertEquals(Layout.QWERTY, m.next(Layout.DEVA_VOWELS, m.KEY_MODE_CHANGE))
    }

    @Test
    fun `lang toggle enters devanagari from qwerty and symbols`() {
        assertEquals(Layout.DEVA_CONSONANTS, m.next(Layout.QWERTY, m.KEY_LANG_TOGGLE))
        assertEquals(Layout.DEVA_CONSONANTS, m.next(Layout.SYMBOLS, m.KEY_LANG_TOGGLE))
    }

    @Test
    fun `lang toggle pages between consonants and vowels`() {
        assertEquals(Layout.DEVA_VOWELS, m.next(Layout.DEVA_CONSONANTS, m.KEY_LANG_TOGGLE))
        assertEquals(Layout.DEVA_CONSONANTS, m.next(Layout.DEVA_VOWELS, m.KEY_LANG_TOGGLE))
    }

    @Test
    fun `abc key returns to qwerty from every layout`() {
        for (l in Layout.values()) {
            assertEquals(Layout.QWERTY, m.next(l, m.KEY_TO_QWERTY))
        }
    }

    @Test
    fun `consonants key lands on the consonant page from every layout`() {
        for (l in Layout.values()) {
            assertEquals(Layout.DEVA_CONSONANTS, m.next(l, m.KEY_TO_CONSONANTS))
        }
    }

    @Test
    fun `ordinary keys never switch layout`() {
        val ordinary = intArrayOf('a'.code, 'z'.code, 2325 /* क */, 32, 10, -1, -5)
        for (l in Layout.values()) {
            for (k in ordinary) {
                assertEquals("layout $l key $k", l, m.next(l, k))
            }
        }
    }

    @Test
    fun `qwerty is reachable from every layout in one press`() {
        // The stuck-keyboard guarantee, stated directly: from ANY layout there is
        // a single key that lands on QWERTY.
        for (l in Layout.values()) {
            assertEquals(Layout.QWERTY, m.next(l, m.KEY_TO_QWERTY))
        }
    }

    @Test
    fun `devanagari flag covers exactly the two hindi pages`() {
        assertTrue(m.isDevanagari(Layout.DEVA_CONSONANTS))
        assertTrue(m.isDevanagari(Layout.DEVA_VOWELS))
        assertFalse(m.isDevanagari(Layout.QWERTY))
        assertFalse(m.isDevanagari(Layout.SYMBOLS))
    }
}
