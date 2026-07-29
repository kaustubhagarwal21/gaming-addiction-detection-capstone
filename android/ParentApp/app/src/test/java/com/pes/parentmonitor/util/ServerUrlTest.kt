package com.pes.parentmonitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerUrlTest {
    @Test
    fun `normalizes a valid root https base URL`() {
        assertEquals(
            "https://example.com/",
            ServerUrl.normalize(" https://EXAMPLE.com:443 ", allowInsecureLan = false)
        )
        assertNull(ServerUrl.normalize("https://example.com/api", allowInsecureLan = false))
    }

    @Test
    fun `rejects credentials query fragment and malformed URLs`() {
        assertNull(ServerUrl.normalize("not a url", allowInsecureLan = true))
        assertNull(ServerUrl.normalize("https://u:p@example.com/", allowInsecureLan = true))
        assertNull(ServerUrl.normalize("https://example.com/?token=x", allowInsecureLan = true))
        assertNull(ServerUrl.normalize("https://example.com/#x", allowInsecureLan = true))
    }

    @Test
    fun `release cleartext is loopback only`() {
        assertNull(ServerUrl.normalize("http://192.168.1.4:5000", allowInsecureLan = false))
        assertEquals(
            "http://127.0.0.1:5000/",
            ServerUrl.normalize("http://127.0.0.1:5000", allowInsecureLan = false)
        )
        assertEquals(
            "http://192.168.1.4:5000/",
            ServerUrl.normalize("http://192.168.1.4:5000", allowInsecureLan = true)
        )
    }
}
