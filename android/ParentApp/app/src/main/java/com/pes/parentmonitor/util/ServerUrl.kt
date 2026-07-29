package com.pes.parentmonitor.util

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Validates the actual Retrofit base URL, not just the origin used to bind a token.
 *
 * API methods already start with `api/`, so a stored base path would silently target
 * the wrong routes. Credentials, queries, and fragments also do not belong in a
 * backend address. Release builds permit cleartext only for the loopback hosts allowed
 * by the release network-security policy.
 */
object ServerUrl {
    private val releaseHttpHosts = setOf("localhost", "127.0.0.1", "10.0.2.2")

    fun normalize(raw: String?, allowInsecureLan: Boolean): String? {
        val parsed = raw?.trim()?.toHttpUrlOrNull() ?: return null
        if (parsed.scheme != "http" && parsed.scheme != "https") return null
        if (parsed.username.isNotEmpty() || parsed.password.isNotEmpty()) return null
        if (parsed.query != null || parsed.fragment != null) return null
        if (parsed.encodedPath != "/") return null
        if (parsed.scheme == "http" &&
            !allowInsecureLan &&
            parsed.host !in releaseHttpHosts
        ) {
            return null
        }
        val value = parsed.toString()
        return if (value.endsWith('/')) value else "$value/"
    }
}
