package com.pes.parentmonitor.api

import com.pes.parentmonitor.BuildConfig
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import com.pes.parentmonitor.util.ServerOrigin
import com.pes.parentmonitor.util.ServerUrl
import java.util.concurrent.TimeUnit

object ApiClient {
    private const val SKIP_AUTH_HEADER = "X-Parent-Skip-Auth"
    private var retrofit: Retrofit? = null
    private var currentBaseUrl: String = ""
    private val authSessions = AuthSessionStore()

    fun installAuthSession(token: String?, baseUrlOrOrigin: String?) {
        authSessions.install(token, ServerOrigin.normalize(baseUrlOrOrigin))
    }

    fun restoreAuthSession(token: String?, baseUrlOrOrigin: String?) {
        authSessions.restore(token, ServerOrigin.normalize(baseUrlOrOrigin))
    }

    fun clearAuthSession() = authSessions.clear()

    // Invoked once when the server rejects a token we sent with 401 (session expired
    // after the 30-day TTL, or the signing secret changed). Without this the dashboard
    // would just fail to load with no way back to sign-in. The Application sets it.
    @Volatile
    var onUnauthorized: ((Long) -> Unit)? = null

    /** The main-thread callback must re-check this before clearing persistent state. */
    fun isCurrentUnauthorized(revision: Long): Boolean =
        authSessions.isCurrentInvalidation(revision)

    @Synchronized
    fun getInstance(baseUrl: String): ApiService {
        val normalizedBaseUrl = ServerUrl.normalize(baseUrl, BuildConfig.DEBUG)
            ?: throw IllegalArgumentException("Invalid server base URL")
        if (retrofit == null || currentBaseUrl != normalizedBaseUrl) {
            currentBaseUrl = normalizedBaseUrl
            val clientOrigin = ServerOrigin.normalize(normalizedBaseUrl)
            // BASIC logs method/URL/status only — no PIN or FCM token bodies.
            // NONE in release so nothing reaches logcat.
            val logging = HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
                        else HttpLoggingInterceptor.Level.NONE
            }
            val auth = Interceptor { chain ->
                val original = chain.request()
                val skipAuth = original.header(SKIP_AUTH_HEADER).equals("true", ignoreCase = true)
                val snapshot = if (skipAuth) null else authSessions.snapshotFor(clientOrigin)
                val req = original.newBuilder()
                    .removeHeader(SKIP_AUTH_HEADER)
                    .apply {
                        snapshot?.let { header("Authorization", "Bearer ${it.token}") }
                    }
                    .build()
                val response = chain.proceed(req)
                // Only the exact auth revision carried by this request may be invalidated.
                // A slow 401 from an older login/origin is ignored.
                if (response.code == 401 && snapshot != null) {
                    authSessions.invalidateIfCurrent(snapshot)?.let { revision ->
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
