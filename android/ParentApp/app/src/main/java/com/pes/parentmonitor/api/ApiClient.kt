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
                chain.proceed(req)
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
