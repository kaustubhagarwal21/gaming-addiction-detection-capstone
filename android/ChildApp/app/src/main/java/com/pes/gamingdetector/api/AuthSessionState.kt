package com.pes.gamingdetector.api

import com.pes.gamingdetector.util.ServerUrl
import java.util.concurrent.atomic.AtomicReference

/**
 * Process-local bearer-token state.
 *
 * A token is bound to the normalized Retrofit base URL that issued it.  Each installation
 * creates a distinct [BoundToken] generation, so a late 401 for an older login cannot clear
 * a newer login even when the server happened to issue the same token text.
 */
internal class AuthSessionState {
    internal class BoundToken(
        val value: String,
        val baseUrl: String
    )

    private data class State(
        val token: BoundToken?,
        val restoreBlocked: Boolean,
        val revision: Long,
    )

    private val state = AtomicReference(
        State(token = null, restoreBlocked = false, revision = 0L)
    )

    fun install(value: String?, baseUrl: String?): BoundToken? {
        val token = value?.trim()?.takeIf { it.isNotEmpty() }
        val normalized = normalizeBaseUrl(baseUrl)
        val bound = if (token != null && normalized != null) BoundToken(token, normalized) else null
        while (true) {
            val current = state.get()
            if (state.compareAndSet(
                    current,
                    State(bound, restoreBlocked = false, revision = current.revision + 1)
                )) {
                return bound
            }
        }
    }

    /**
     * Restore after process/component creation, but never resurrect a disk token after the
     * current process has already rejected it.  A live installed token also always wins over
     * a later stale preference read.
     */
    fun restore(value: String?, baseUrl: String?): BoundToken? {
        val token = value?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        val normalized = normalizeBaseUrl(baseUrl) ?: return null
        while (true) {
            val current = state.get()
            if (current.restoreBlocked || current.token != null) return current.token
            val restored = BoundToken(token, normalized)
            if (state.compareAndSet(
                    current,
                    State(
                        restored,
                        restoreBlocked = false,
                        revision = current.revision + 1,
                    )
                )) {
                return restored
            }
        }
    }

    /** Return a generation only to the exact normalized backend that issued it. */
    fun tokenFor(baseUrl: String): BoundToken? {
        val normalized = normalizeBaseUrl(baseUrl) ?: return null
        return state.get().token?.takeIf { it.baseUrl == normalized }
    }

    /**
     * Invalidate only the exact generation carried by the rejected request.  Object identity
     * is deliberate: a newer login can legitimately have identical token text and base URL.
     */
    fun invalidateIfCurrent(rejected: BoundToken): Long? {
        while (true) {
            val current = state.get()
            if (current.token !== rejected) return null
            val invalidationRevision = current.revision + 1
            if (state.compareAndSet(
                    current,
                    State(
                        token = null,
                        restoreBlocked = true,
                        revision = invalidationRevision,
                    )
                )) {
                return invalidationRevision
            }
        }
    }

    fun clear() {
        // Block stale preference reads until a real login installs a new generation.
        while (true) {
            val current = state.get()
            if (state.compareAndSet(
                    current,
                    State(
                        token = null,
                        restoreBlocked = true,
                        revision = current.revision + 1,
                    )
                )) {
                return
            }
        }
    }

    fun currentToken(): String? = state.get().token?.value

    /** True only while this exact invalidation is still current (no newer login/clear). */
    fun isCurrentInvalidation(revision: Long): Boolean {
        val current = state.get()
        return current.revision == revision &&
            current.token == null &&
            current.restoreBlocked
    }

    companion object {
        fun normalizeBaseUrl(raw: String?): String? {
            // Auth binding cares about an exact backend root. It deliberately does not
            // decide whether LAN HTTP is allowed (that is build-specific and enforced by
            // ApiClient), but it must reject paths/credentials/query/fragment just like
            // the server-setup UI. Otherwise a corrupt legacy preference can bind a token
            // to a different request target than the one the UI accepted.
            return raw?.let { ServerUrl.normalize(it, allowInsecureLan = true) }
        }

        /** Public endpoints must never receive or invalidate a bearer token. */
        fun isPublicPath(encodedPath: String): Boolean {
            val path = encodedPath.trimEnd('/').ifEmpty { "/" }
            return path in setOf(
                "/api/health",
                "/api/user/login",
                "/api/register",
                "/api/model_card",
                "/api/model-card"
            )
        }
    }
}
