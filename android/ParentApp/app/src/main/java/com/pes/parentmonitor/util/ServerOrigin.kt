package com.pes.parentmonitor.util

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Canonical scheme + host + effective port used to bind a bearer token to the
 * backend that issued it. Paths intentionally do not participate in the origin.
 */
object ServerOrigin {
    fun normalize(value: String?): String? {
        val url = value?.trim()?.toHttpUrlOrNull() ?: return null
        if (url.scheme != "http" && url.scheme != "https") return null
        return url.newBuilder()
            .username("")
            .password("")
            .encodedPath("/")
            .query(null)
            .fragment(null)
            .build()
            .toString()
            .removeSuffix("/")
    }
}
