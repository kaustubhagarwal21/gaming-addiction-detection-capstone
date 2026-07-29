package com.pes.gamingdetector.util

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** Validation shared by server setup and its connection test. Retrofit base URLs must
 * be absolute HTTP(S) URLs ending in '/', and credentials/query/fragment do not belong
 * in a backend origin. Release builds allow cleartext only for the loopback hosts that
 * the release network-security policy explicitly permits. */
object ServerUrl {
    private val releaseHttpHosts = setOf("localhost", "127.0.0.1", "10.0.2.2")

    fun normalize(raw: String, allowInsecureLan: Boolean): String? {
        val parsed = raw.trim().toHttpUrlOrNull() ?: return null
        if (parsed.scheme != "http" && parsed.scheme != "https") return null
        if (parsed.username.isNotEmpty() || parsed.password.isNotEmpty()) return null
        if (parsed.query != null || parsed.fragment != null) return null
        // Retrofit methods already begin with "api/". Accepting a base path such as
        // https://host/api would silently call https://host/api/api/... instead.
        if (parsed.encodedPath != "/") return null
        if (parsed.scheme == "http" && !allowInsecureLan && parsed.host !in releaseHttpHosts) {
            return null
        }
        val value = parsed.toString()
        return if (value.endsWith('/')) value else "$value/"
    }
}
