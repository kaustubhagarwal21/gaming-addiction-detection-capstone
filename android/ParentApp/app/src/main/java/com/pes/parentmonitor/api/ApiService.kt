package com.pes.parentmonitor.api

import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    @GET("api/health")
    suspend fun health(): Response<HealthResponse>

    @POST("api/user/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @GET("api/dashboard/parent")
    suspend fun getParentalDashboard(@Query("user_id") userId: Int): Response<ParentalDashboard>

    @GET("api/alerts")
    suspend fun getAlerts(@Query("user_id") userId: Int): Response<AlertsResponse>

    @POST("api/alerts/mark_read")
    suspend fun markAlertsRead(@Body request: MarkReadRequest): Response<GenericResponse>

    @GET("api/child/status")
    suspend fun getChildStatus(@Query("user_id") userId: Int): Response<ChildStatusResponse>

    @POST("api/pair")
    suspend fun pairDevices(@Body body: Map<String, Int>): Response<PairResponse>

    @GET("api/dashboard/emotions")
    suspend fun getEmotions(@Query("user_id") userId: Int): Response<EmotionDashboard>

    @GET("api/dashboard/chat_analysis")
    suspend fun getChatAnalysis(@Query("user_id") userId: Int): Response<ChatAnalysisDashboard>

    @POST("api/user/fcm_token")
    suspend fun updateFcmToken(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @POST("api/parent/set_limit")
    suspend fun setTimeLimit(@Body body: @JvmSuppressWildcards Map<String, Any>): Response<GenericResponse>

    @Streaming
    @GET("api/dashboard/weekly_report/pdf")
    suspend fun downloadWeeklyReportPdf(@Query("user_id") userId: Int): Response<ResponseBody>
}
