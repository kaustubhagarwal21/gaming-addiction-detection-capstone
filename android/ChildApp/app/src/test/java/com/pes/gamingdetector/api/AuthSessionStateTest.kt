package com.pes.gamingdetector.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class AuthSessionStateTest {
    @Test
    fun `late 401 cannot clear a newer token generation`() {
        val state = AuthSessionState()
        val old = state.install("old", "https://example.com")!!
        val newer = state.install("new", "https://example.com/")!!

        assertNull(state.invalidateIfCurrent(old))
        assertSame(newer, state.tokenFor("https://example.com"))
        assertEquals("new", state.currentToken())
    }

    @Test
    fun `rejected current token blocks stale disk restoration until login`() {
        val state = AuthSessionState()
        val rejected = state.install("expired", "https://example.com/")!!

        val revision = state.invalidateIfCurrent(rejected)
        assertTrue(revision != null)
        assertTrue(state.isCurrentInvalidation(revision!!))
        assertNull(state.restore("expired", "https://example.com/"))
        assertNull(state.currentToken())

        state.install("fresh", "https://example.com/")
        assertFalse(state.isCurrentInvalidation(revision))
        assertEquals("fresh", state.currentToken())
    }

    @Test
    fun `token is bound to normalized issuing base URL`() {
        val state = AuthSessionState()
        state.install("secret", "https://EXAMPLE.com:443")

        assertEquals("secret", state.tokenFor("https://example.com/")?.value)
        assertNull(state.tokenFor("https://other.example/"))
    }

    @Test
    fun `unsafe or non-root issuing URLs cannot bind a token`() {
        for (url in listOf(
            "https://example.com/api",
            "https://user:pass@example.com/",
            "https://example.com/?token=secret",
            "https://example.com/#fragment",
        )) {
            val state = AuthSessionState()
            assertNull(url, state.install("secret", url))
            assertNull(url, state.currentToken())
        }
    }

    @Test
    fun `public routes never qualify for bearer authentication`() {
        for (path in listOf(
            "/api/health", "/api/health/", "/api/user/login",
            "/api/register", "/api/model_card", "/api/model-card"
        )) {
            assertTrue(path, AuthSessionState.isPublicPath(path))
        }
        assertFalse(AuthSessionState.isPublicPath("/api/dashboard/user"))
    }
}
