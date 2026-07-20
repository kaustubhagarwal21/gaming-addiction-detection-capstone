package com.pes.parentmonitor.util

import com.pes.parentmonitor.util.ProfileValidation.Result
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileValidationTest {

    @Test
    fun `name is trimmed and required`() {
        assertEquals(Result.Ok("Arjun"), ProfileValidation.validateName("  Arjun  "))
        assertTrue(ProfileValidation.validateName("   ") is Result.Error)
        assertTrue(ProfileValidation.validateName(null) is Result.Error)
        assertTrue(ProfileValidation.validateName("x".repeat(41)) is Result.Error)
    }

    @Test
    fun `age must be a number in 1 to 100`() {
        assertEquals(Result.Ok("15"), ProfileValidation.validateAge("15"))
        assertEquals(Result.Ok("1"), ProfileValidation.validateAge(" 1 "))
        assertEquals(Result.Ok("100"), ProfileValidation.validateAge("100"))
        assertTrue(ProfileValidation.validateAge("0") is Result.Error)
        assertTrue(ProfileValidation.validateAge("101") is Result.Error)
        assertTrue(ProfileValidation.validateAge("ten") is Result.Error)
        assertTrue(ProfileValidation.validateAge("") is Result.Error)
    }

    @Test
    fun `blank pin means unchanged, otherwise 4 to 6 digits`() {
        assertEquals(Result.Ok(""), ProfileValidation.validateOptionalPin(""))
        assertEquals(Result.Ok(""), ProfileValidation.validateOptionalPin("   "))
        assertEquals(Result.Ok("1234"), ProfileValidation.validateOptionalPin("1234"))
        assertEquals(Result.Ok("123456"), ProfileValidation.validateOptionalPin("123456"))
        assertTrue(ProfileValidation.validateOptionalPin("123") is Result.Error)      // too short
        assertTrue(ProfileValidation.validateOptionalPin("1234567") is Result.Error)  // too long
        assertTrue(ProfileValidation.validateOptionalPin("12ab") is Result.Error)     // non-digit
    }
}
