package com.pes.parentmonitor.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AuthSessionStoreTest {
    @Test
    fun `stale 401 cannot invalidate a newer login`() {
        val store = AuthSessionStore()
        store.install("old", "https://one.example")
        val oldRequest = store.snapshotFor("https://one.example")!!

        store.install("new", "https://one.example")

        assertNull(store.invalidateIfCurrent(oldRequest))
        assertEquals("new", store.snapshotFor("https://one.example")?.token)
    }

    @Test
    fun `token is sent only to its issuing origin`() {
        val store = AuthSessionStore()
        store.install("secret", "https://one.example")

        assertNotNull(store.snapshotFor("https://one.example"))
        assertNull(store.snapshotFor("https://two.example"))
    }

    @Test
    fun `persisted bearer token is trimmed and blank tokens are rejected`() {
        val store = AuthSessionStore()
        store.restore("  secret  ", "https://one.example")
        assertEquals("secret", store.snapshotFor("https://one.example")?.token)

        store.install("   ", "https://one.example")
        assertNull(store.snapshotFor("https://one.example"))
    }

    @Test
    fun `rejected disk token cannot be restored before a real login`() {
        val store = AuthSessionStore()
        store.install("expired", "https://one.example")
        val request = store.snapshotFor("https://one.example")!!
        val revision = store.invalidateIfCurrent(request)!!

        assertTrue(store.isCurrentInvalidation(revision))
        store.restore("expired", "https://one.example")
        assertNull(store.snapshotFor("https://one.example"))

        store.install("fresh", "https://one.example")
        assertFalse(store.isCurrentInvalidation(revision))
        assertEquals("fresh", store.snapshotFor("https://one.example")?.token)
    }
}
