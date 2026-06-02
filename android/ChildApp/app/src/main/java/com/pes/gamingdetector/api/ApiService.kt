package com.pes.gamingdetector.api

import okhttp3.MultipartBody
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    @GET("api/health")
    suspend fun health(): Response<HealthResponse>

    @POST("api/user/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @POST("api/register")
    suspend fun register(@Body request: RegisterRequest): Response<LoginResponse>

    @POST("api/session/start")
    suspend fun startSession(@Body request: StartSessionRequest): Response<SessionResponse>

    @POST("api/session/{id}/end")
    suspend fun endSession(
        @Path("id") sessionId: Int,
        // Seconds before now the player actually stopped (grace/ancillary tail). 0 = end now.
        @Query("ended_seconds_ago") endedSecondsAgo: Long = 0
    ): Response<EndSessionResponse>

    @POST("api/session/{id}/predict")
    suspend fun livePrediction(@Path("id") sessionId: Int): Response<LivePrediction>

    @Multipart
    @POST("api/session/{id}/voice")
    suspend fun uploadVoice(
        @Path("id") sessionId: Int,
        @Part audio: MultipartBody.Part
    ): Response<VoiceResponse>

    @POST("api/session/{id}/chat")
    suspend fun uploadChat(
        @Path("id") sessionId: Int,
        @Body body: Map<String, String>
    ): Response<GenericResponse>

    @GET("api/games")
    suspend fun getGames(): Response<GamesResponse>

    @GET("api/dashboard/child_enriched")
    suspend fun getChildEnriched(@Query("user_id") userId: Int): Response<ChildEnrichedResponse>

    @POST("api/child/screen_event")
    suspend fun postScreenEvent(@Body body: Map<String, String>): Response<GenericResponse>

    @POST("api/child/notification_event")
    suspend fun postNotificationEvent(@Body body: Map<String, String>): Response<GenericResponse>

    @GET("api/dashboard/user")
    suspend fun getUserDashboard(@Query("user_id") userId: Int): Response<UserDashboard>

    @GET("api/sessions")
    suspend fun getSessions(
        @Query("user_id") userId: Int,
        @Query("limit") limit: Int = 50
    ): Response<List<SessionRow>>

    // ── Counselor chatbot ──────────────────────────────────────────
    @POST("api/counselor/chat")
    suspend fun counselorChat(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<CounselorReplyResponse>

    @GET("api/counselor/history")
    suspend fun counselorHistory(@Query("user_id") userId: Int): Response<CounselorHistoryResponse>

    // ── Daily reflection ───────────────────────────────────────────
    @POST("api/child/reflection")
    suspend fun postReflection(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @GET("api/child/reflections")
    suspend fun getReflections(
        @Query("user_id") userId: Int,
        @Query("days") days: Int = 14
    ): Response<ReflectionsResponse>

    // ── Privacy: consent + data deletion ───────────────────────────
    @GET("api/consent")
    suspend fun getConsent(@Query("user_id") userId: Int): Response<ConsentStatus>

    @POST("api/consent")
    suspend fun postConsent(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @POST("api/user/delete_data")
    suspend fun deleteData(@Body body: Map<String, String>): Response<GenericResponse>
}
