package com.pes.gamingdetector.api

import com.pes.gamingdetector.BuildConfig
import com.pes.gamingdetector.util.ServerUrl
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    private var retrofit: Retrofit? = null
    private var currentBaseUrl: String = ""

    private val authState = AuthSessionState()
    val authToken: String?
        get() = authState.currentToken()

    // Invoked once when the server rejects a token we sent with 401 (session expired
    // after the 30-day TTL, or the signing secret changed). Without this the app would
    // silently fail every request forever. The Application sets it to force re-login.
    @Volatile
    var onUnauthorized: ((Long) -> Unit)? = null

    /** Install a token returned by a successful login/registration. This is the only
     * path that re-arms 401 handling: repeatedly constructing PrefsManager must not
     * resurrect a token that an in-flight 401 has already invalidated. */
    fun installLoginToken(value: String?, baseUrl: String?) {
        authState.install(value, baseUrl)
    }

    /** Restore the persisted token after process/component creation. Once a 401 has
     * invalidated the current token, ignore stale disk reads until a real login installs
     * a new token. This closes the 401 -> PrefsManager init -> old-token resurrection race. */
    fun restorePersistedToken(value: String?, baseUrl: String?) {
        authState.restore(value, baseUrl)
    }

    /** Clear the in-memory token without pretending a new login occurred. */
    fun clearAuthToken() {
        authState.clear()
    }

    /** Re-check after hopping from the OkHttp thread to the main thread. */
    fun isCurrentUnauthorized(revision: Long): Boolean =
        authState.isCurrentInvalidation(revision)

    @Synchronized
    fun getInstance(baseUrl: String): ApiService {
        // Re-validate at the network boundary. Settings normally stores a validated
        // value, but old/corrupt preferences and background workers must not bypass the
        // release HTTPS policy or smuggle a base path/credentials into Retrofit.
        val normalizedBaseUrl = ServerUrl.normalize(baseUrl, BuildConfig.DEBUG)
            ?: throw IllegalArgumentException("Invalid server base URL")
        if (retrofit == null || currentBaseUrl != normalizedBaseUrl) {
            currentBaseUrl = normalizedBaseUrl
            // BASIC logs method/URL/status — no PIN, chat text, or FCM token.
            // NONE in release so nothing reaches logcat.
            val logging = HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
                        else HttpLoggingInterceptor.Level.NONE
            }
            val auth = Interceptor { chain ->
                val original = chain.request()
                val publicEndpoint = AuthSessionState.isPublicPath(original.url.encodedPath)
                val generation = if (publicEndpoint) null else authState.tokenFor(normalizedBaseUrl)
                val req = when {
                    publicEndpoint -> original.newBuilder()
                        .removeHeader("Authorization")
                        .build()
                    generation != null -> original.newBuilder()
                        .header("Authorization", "Bearer ${generation.value}")
                        .build()
                    else -> original
                }
                val response = chain.proceed(req)
                // Invalidate only the exact token generation this request carried. A late
                // 401 from a previous account/login must never clear a newer token.
                if (response.code == 401 && generation != null) {
                    authState.invalidateIfCurrent(generation)?.let { revision ->
                        onUnauthorized?.invoke(revision)
                    }
                }
                response
            }
            val client = OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(90, TimeUnit.SECONDS)   // tolerate cloud (Render) cold-start wake-ups
                .writeTimeout(60, TimeUnit.SECONDS)
                .addInterceptor(auth)
                .addInterceptor(logging)
                .build()

            retrofit = Retrofit.Builder()
                .baseUrl(normalizedBaseUrl)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
        }
        return retrofit!!.create(ApiService::class.java)
    }
}
