package com.pes.parentmonitor.api

import com.pes.parentmonitor.BuildConfig
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    private var retrofit: Retrofit? = null
    private var currentBaseUrl: String = ""

    // Signed bearer token from login. Kept in sync with persistent storage by
    // PrefsManager (set on login, refreshed whenever a PrefsManager is created,
    // cleared on logout). The interceptor attaches it to every request.
    @Volatile
    var authToken: String? = null
        set(value) {
            field = value
            if (!value.isNullOrEmpty()) unauthorizedSignaled = false  // fresh login re-arms
        }

    // Invoked once when the server rejects a token we sent with 401 (session expired
    // after the 30-day TTL, or the signing secret changed). Without this the dashboard
    // would just fail to load with no way back to sign-in. The Application sets it.
    @Volatile
    var onUnauthorized: (() -> Unit)? = null
    @Volatile
    private var unauthorizedSignaled = false

    @Synchronized
    fun getInstance(baseUrl: String): ApiService {
        if (retrofit == null || currentBaseUrl != baseUrl) {
            currentBaseUrl = baseUrl
            // BASIC logs method/URL/status only — no PIN or FCM token bodies.
            // NONE in release so nothing reaches logcat.
            val logging = HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
                        else HttpLoggingInterceptor.Level.NONE
            }
            val auth = Interceptor { chain ->
                val tok = authToken
                val req = if (!tok.isNullOrEmpty())
                    chain.request().newBuilder()
                        .header("Authorization", "Bearer $tok").build()
                else chain.request()
                val response = chain.proceed(req)
                // A 401 on a request that carried a token (never the login call) means
                // the token is dead. Signal exactly once so the app can clear the
                // session and return to sign-in instead of failing silently.
                if (response.code == 401 && !tok.isNullOrEmpty() &&
                    !req.url.encodedPath.contains("login") && !unauthorizedSignaled) {
                    unauthorizedSignaled = true
                    authToken = null
                    onUnauthorized?.invoke()
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
                .baseUrl(baseUrl)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
        }
        return retrofit!!.create(ApiService::class.java)
    }
}
