package com.pes.gamingdetector.api

import com.google.gson.annotations.SerializedName

data class LoginRequest(val pin: String, val role: String = "child")
data class LoginResponse(
    val success: Boolean,
    @SerializedName("user_id") val userId: Int,
    val name: String,
    val role: String,
    val token: String?,
    val message: String?
)

data class ConsentStatus(
    val success: Boolean = false,
    @SerializedName("consent_given") val consentGiven: Boolean = false,
    @SerializedName("needs_consent") val needsConsent: Boolean = true,
    @SerializedName("current_version") val currentVersion: String? = null
)

data class StartSessionRequest(
    @SerializedName("user_id") val userId: Int,
    @SerializedName("game_name") val gameName: String
)

data class SessionResponse(
    val success: Boolean,
    @SerializedName("session_id") val sessionId: Int,
    val message: String?
)

data class EndSessionResponse(
    val success: Boolean,
    val prediction: Prediction?,
    val message: String?
)

data class TopFactor(
    val feature: String,
    val label: String,
    val value: Double,
    @SerializedName("contribution_pct") val contributionPct: Double
)

data class Prediction(
    @SerializedName("risk_label") val riskLabel: String,
    @SerializedName("risk_score") val riskScore: Double,
    @SerializedName("behavior_score") val behaviorScore: Double,
    @SerializedName("chat_score") val chatScore: Double,
    @SerializedName("voice_score") val voiceScore: Double,
    val recommendations: List<String>?,
    @SerializedName("top_factors") val topFactors: List<TopFactor>?,
    @SerializedName("observation_mode") val observationMode: Boolean?,
    @SerializedName("sessions_analyzed") val sessionsAnalyzed: Int?,
    @SerializedName("short_session_note") val shortSessionNote: String?
)

data class Game(
    val id: Int,
    val name: String,
    @SerializedName("package_name") val packageName: String?,
    @SerializedName("icon_url") val iconUrl: String?
)

data class UserDashboard(
    val success: Boolean,
    val stats: DashboardStats?,
    @SerializedName("recent_sessions") val recentSessions: List<SessionSummary>?,
    @SerializedName("trend_data") val trendData: List<TrendPoint>?
)

data class DashboardStats(
    @SerializedName("total_sessions") val totalSessions: Int,
    @SerializedName("total_hours") val totalHours: Double,
    @SerializedName("current_risk") val currentRisk: String,
    @SerializedName("risk_score") val riskScore: Double,
    @SerializedName("avg_daily_hours") val avgDailyHours: Double
)

data class SessionSummary(
    val id: Int,
    @SerializedName("game_name") val gameName: String,
    @SerializedName("risk_label") val riskLabel: String,
    @SerializedName("risk_score") val riskScore: Double,
    val duration: String,
    @SerializedName("created_at") val createdAt: String
)

data class TrendPoint(
    val date: String,
    val score: Double,
    val label: String
)

data class VoiceResponse(
    val success: Boolean,
    val emotion: String?,
    val score: Double?
)

data class HealthResponse(
    val status: String,
    @SerializedName("models_loaded") val modelsLoaded: Boolean
)

data class GamesResponse(
    val success: Boolean,
    val games: List<Game>
)

data class LivePrediction(
    val success: Boolean,
    @SerializedName("risk_label") val riskLabel: String?,
    @SerializedName("risk_score") val riskScore: Double?
)

data class GenericResponse(val success: Boolean, val message: String?)

data class ChildEnrichedResponse(
    val success: Boolean,
    val streak: StreakInfo?,
    @SerializedName("limit_status") val limitStatus: LimitStatus?,
    @SerializedName("self_awareness_message") val selfAwarenessMessage: String?
)

data class StreakInfo(
    @SerializedName("current_streak") val currentStreak: Int,
    @SerializedName("longest_streak") val longestStreak: Int,
    @SerializedName("total_healthy_days") val totalHealthyDays: Int
)

data class LimitStatus(
    @SerializedName("daily_limit_hours") val dailyLimitHours: Double,
    @SerializedName("used_today_hours") val usedTodayHours: Double,
    @SerializedName("remaining_hours") val remainingHours: Double,
    val exceeded: Boolean
)

data class SessionRow(
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("game_name") val gameName: String?,
    @SerializedName("start_time") val startTime: String?,
    @SerializedName("duration_seconds") val durationSeconds: Int?,
    @SerializedName("final_risk_score") val finalRiskScore: Double?,
    @SerializedName("risk_category") val riskCategory: String?,
    @SerializedName("chat_count") val chatCount: Int?,
    @SerializedName("voice_count") val voiceCount: Int?
)

// ── Counselor chatbot ───────────────────────────────────────────────
data class CounselorReplyResponse(
    val success: Boolean,
    val reply: String,
    val intent: String?
)

data class CounselorMessage(
    val role: String,
    val content: String,
    @SerializedName("created_at") val createdAt: String?
)

data class CounselorHistoryResponse(
    val success: Boolean,
    val messages: List<CounselorMessage>
)

// ── Reflection ──────────────────────────────────────────────────────
data class Reflection(
    @SerializedName("mood_rating") val moodRating: Int?,
    @SerializedName("sleep_quality") val sleepQuality: Int?,
    @SerializedName("energy_level") val energyLevel: Int?,
    val note: String?,
    @SerializedName("created_at") val createdAt: String?
)

data class ReflectionsResponse(
    val success: Boolean,
    val reflections: List<Reflection>
)
