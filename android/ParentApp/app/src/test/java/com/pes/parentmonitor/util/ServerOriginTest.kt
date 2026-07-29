package com.pes.parentmonitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerOriginTest {
    @Test
    fun `normalization ignores paths credentials case and default ports`() {
        assertEquals(
            "https://example.com",
            ServerOrigin.normalize(" HTTPS://user:pass@EXAMPLE.com:443/a/backend/?q=1#part ")
        )
        assertEquals(
            "http://example.com",
            ServerOrigin.normalize("http://example.com:80/")
        )
    }

    @Test
    fun `different effective ports remain different origins`() {
        assertEquals("https://example.com:8443", ServerOrigin.normalize("https://example.com:8443/api/"))
    }

    @Test
    fun `invalid values do not create an origin`() {
        assertNull(ServerOrigin.normalize(null))
        assertNull(ServerOrigin.normalize("example.com"))
        assertNull(ServerOrigin.normalize("ftp://example.com/"))
    }
}
