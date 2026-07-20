package com.pes.parentmonitor.util

/**
 * Pure client-side validation for the parent-controlled child-profile edit, mirroring
 * the server's rules (name non-blank; age 1..100; PIN 4-6 digits) so bad input is
 * caught before a round trip. Kept free of Android types for plain-JVM unit tests.
 */
object ProfileValidation {
    const val NAME_MAX = 40
    val PIN_REGEX = Regex("""^\d{4,6}$""")

    /** Trimmed name if usable, else an error string. */
    fun validateName(raw: String?): Result {
        val name = raw?.trim().orEmpty()
        return when {
            name.isEmpty() -> Result.Error("Name can't be empty")
            name.length > NAME_MAX -> Result.Error("Name is too long (max $NAME_MAX)")
            else -> Result.Ok(name)
        }
    }

    /** Age as an Int if in range, else an error. */
    fun validateAge(raw: String?): Result {
        val age = raw?.trim()?.toIntOrNull()
        return when {
            age == null -> Result.Error("Enter a number for age")
            age !in 1..100 -> Result.Error("Age must be between 1 and 100")
            else -> Result.Ok(age.toString())
        }
    }

    /** A NEW child PIN, only if the field is non-blank (blank = leave PIN unchanged). */
    fun validateOptionalPin(raw: String?): Result {
        val pin = raw?.trim().orEmpty()
        return when {
            pin.isEmpty() -> Result.Ok("")                 // unchanged
            !PIN_REGEX.matches(pin) -> Result.Error("PIN must be 4-6 digits")
            else -> Result.Ok(pin)
        }
    }

    sealed class Result {
        data class Ok(val value: String) : Result()
        data class Error(val message: String) : Result()
    }
}
