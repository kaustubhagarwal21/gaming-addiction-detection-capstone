package com.pes.parentmonitor.api

/**
 * Small synchronized auth state machine shared by every Retrofit client.
 *
 * A request receives a [Snapshot]. A 401 may invalidate the session only while that
 * exact revision is still current, so a late response from an older login cannot
 * erase a newer token.
 */
internal class AuthSessionStore {
    data class Snapshot(
        val token: String,
        val origin: String,
        val revision: Long
    )

    private data class State(
        val token: String?,
        val origin: String?,
        val revision: Long
    )

    private var state = State(null, null, 0)
    private var restoreBlocked = false

    @Synchronized
    fun install(token: String?, origin: String?) {
        val cleanToken = token?.trim()?.takeIf { it.isNotEmpty() }
        state = if (cleanToken == null || origin.isNullOrBlank()) {
            State(null, null, state.revision + 1)
        } else {
            State(cleanToken, origin, state.revision + 1)
        }
        restoreBlocked = false
    }

    /** Restore after process recreation, but never revive the token just rejected by a 401. */
    @Synchronized
    fun restore(token: String?, origin: String?) {
        val cleanToken = token?.trim()?.takeIf { it.isNotEmpty() }
        if (restoreBlocked || state.token != null || cleanToken == null || origin.isNullOrBlank()) {
            return
        }
        state = State(cleanToken, origin, state.revision + 1)
    }

    @Synchronized
    fun clear() {
        state = State(null, null, state.revision + 1)
        restoreBlocked = false
    }

    @Synchronized
    fun snapshotFor(origin: String?): Snapshot? {
        val current = state
        if (origin == null || current.origin != origin || current.token.isNullOrBlank()) return null
        return Snapshot(current.token, current.origin, current.revision)
    }

    /**
     * @return the invalidation revision, or null when this response belongs to an
     * older/different session and must be ignored.
     */
    @Synchronized
    fun invalidateIfCurrent(snapshot: Snapshot): Long? {
        val current = state
        if (current.revision != snapshot.revision ||
            current.token != snapshot.token ||
            current.origin != snapshot.origin
        ) {
            return null
        }
        val invalidationRevision = current.revision + 1
        state = State(null, null, invalidationRevision)
        restoreBlocked = true
        return invalidationRevision
    }

    @Synchronized
    fun isCurrentInvalidation(revision: Long): Boolean =
        restoreBlocked && state.revision == revision && state.token == null
}
