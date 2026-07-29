package com.pes.parentmonitor.api

import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    @Headers("X-Parent-Skip-Auth: true")
    @GET("api/health")
    suspend fun health(): Response<HealthResponse>

    @Headers("X-Parent-Skip-Auth: true")
    @GET("api/model_card")
    suspend fun getModelCard(): Response<ModelCard>

    @Headers("X-Parent-Skip-Auth: true")
    @POST("api/user/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @GET("api/dashboard/parent")
    suspend fun getParentalDashboard(@Query("user_id") userId: Int): Response<ParentalDashboard>

    @GET("api/parent/children")
    suspend fun getChildren(): Response<ChildrenResponse>

    @GET("api/alerts")
    suspend fun getAlerts(@Query("user_id") userId: Int): Response<AlertsResponse>

    @POST("api/alerts/mark_read")
    suspend fun markAlertsRead(@Body request: MarkReadRequest): Response<GenericResponse>

    @POST("api/feedback")
    suspend fun submitFeedback(@Body request: FeedbackRequest): Response<GenericResponse>

    @GET("api/feedback/summary")
    suspend fun getFeedbackSummary(@Query("user_id") userId: Int): Response<FeedbackSummary>

    @GET("api/child/status")
    suspend fun getChildStatus(@Query("user_id") userId: Int): Response<ChildStatusResponse>

    @GET("api/dashboard/emotions")
    suspend fun getEmotions(@Query("user_id") userId: Int): Response<EmotionDashboard>

    @GET("api/dashboard/chat_analysis")
    suspend fun getChatAnalysis(@Query("user_id") userId: Int): Response<ChatAnalysisDashboard>

    @POST("api/user/fcm_token")
    suspend fun updateFcmToken(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    // Deregister this device's push token on logout so it stops receiving the family's
    // alerts (otherwise a logged-out phone keeps getting them until the token is reused).
    @Headers("X-Parent-Skip-Auth: true")
    @POST("api/user/fcm_token/unregister")
    suspend fun unregisterFcmToken(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @POST("api/parent/set_limit")
    suspend fun setTimeLimit(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @POST("api/parent/nudge")
    suspend fun sendNudge(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @POST("api/user/delete_data")
    suspend fun deleteData(@Body body: Map<String, String>): Response<GenericResponse>

    @GET("api/user/profile")
    suspend fun getProfile(@Query("user_id") userId: Int): Response<ChildProfile>

    @POST("api/user/update")
    suspend fun updateProfile(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @Streaming
    @GET("api/dashboard/weekly_report/pdf")
    suspend fun downloadWeeklyReportPdf(@Query("user_id") userId: Int): Response<ResponseBody>
}
