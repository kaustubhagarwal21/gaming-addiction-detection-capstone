package com.pes.gamingdetector.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerUrlTest {
    @Test fun `normalizes valid https base URL`() {
        assertEquals("https://example.com/", ServerUrl.normalize(" https://example.com ", false))
        assertNull(ServerUrl.normalize("https://example.com/api", false))
    }

    @Test fun `rejects malformed credentials query and fragment`() {
        assertNull(ServerUrl.normalize("not a url", true))
        assertNull(ServerUrl.normalize("https://u:p@example.com/", true))
        assertNull(ServerUrl.normalize("https://example.com/?token=x", true))
        assertNull(ServerUrl.normalize("https://example.com/#x", true))
    }

    @Test fun `release cleartext is loopback only`() {
        assertNull(ServerUrl.normalize("http://192.168.1.4:5000", false))
        assertEquals("http://127.0.0.1:5000/", ServerUrl.normalize("http://127.0.0.1:5000", false))
        assertEquals("http://192.168.1.4:5000/", ServerUrl.normalize("http://192.168.1.4:5000", true))
    }
}
