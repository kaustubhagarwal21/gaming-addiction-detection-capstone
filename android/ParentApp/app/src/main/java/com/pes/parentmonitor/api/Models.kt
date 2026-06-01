package com.pes.parentmonitor.api

import com.google.gson.annotations.SerializedName

data class LoginRequest(val pin: String, val role: String = "parent")
data class ChildInfo(
    @SerializedName("user_id") val userId: Int,
    val name: String,
    val age: Int?
)
data class LoginResponse(
    val success: Boolean,
    @SerializedName("user_id") val userId: Int,
    val name: String,
    val role: String,
    @SerializedName("child_user_id") val childUserId: Int?,
    val children: List<ChildInfo>?,
    val token: String?,
    val message: String?
)

data class TimeLimitSuggestion(
    @SerializedName("suggested_daily_hours") val suggestedDailyHours: Double,
    @SerializedName("current_avg_daily_hours") val currentAvgDailyHours: Double,
    val reason: String,
    val urgency: String
)

data class PeerComparison(
    @SerializedName("weekly_hours") val weeklyHours: Double,
    val percentile: Int,
    val level: String,
    val message: String
)

data class SleepImpact(
    val available: Boolean,
    @SerializedName("late_night_sessions") val lateNightSessions: Int?,
    @SerializedName("total_days_analyzed") val totalDaysAnalyzed: Int?,
    @SerializedName("late_night_percent") val lateNightPercent: Double?,
    @SerializedName("sleep_disruption_days") val sleepDisruptionDays: Int?,
    val message: String?
)

data class RiskFactor(
    val feature: String,
    val label: String,
    val value: Double,
    @SerializedName("contribution_pct") val contributionPct: Double,
    val impact: Double? = null,           // signed SHAP value
    val direction: String? = null         // "raises" | "lowers"
)

data class StreakData(
    @SerializedName("current_streak") val currentStreak: Int,
    @SerializedName("longest_streak") val longestStreak: Int,
    @SerializedName("total_healthy_days") val totalHealthyDays: Int
)

data class AnomalyInfo(
    val message: String,
    val severity: String,
    @SerializedName("z_score") val zScore: Double?
)

data class ParentalDashboard(
    val success: Boolean,
    @SerializedName("child_name") val childName: String?,
    @SerializedName("current_risk") val currentRisk: String?,
    @SerializedName("risk_label") val riskLabel: String?,
    val disclaimer: String?,
    @SerializedName("risk_score") val riskScore: Double?,
    val alerts: List<Alert>?,
    @SerializedName("trend_data") val trendData: List<TrendPoint>?,
    @SerializedName("top_games") val topGames: List<TopGame>?,
    @SerializedName("total_hours_week") val totalHoursWeek: Double?,
    @SerializedName("late_night_count") val lateNightCount: Int?,
    @SerializedName("recommendations") val recommendations: List<String>?,
    @SerializedName("observation_mode") val observationMode: Boolean?,
    @SerializedName("sessions_analyzed") val sessionsAnalyzed: Int?,
    @SerializedName("daily_hours_week") val dailyHoursWeek: List<DailyHoursPoint>?,
    @SerializedName("time_limit_suggestion") val timeLimitSuggestion: TimeLimitSuggestion?,
    @SerializedName("peer_comparison") val peerComparison: PeerComparison?,
    @SerializedName("sleep_impact") val sleepImpact: SleepImpact?,
    @SerializedName("risk_explanation") val riskExplanation: List<RiskFactor>?,
    val streak: StreakData?,
    @SerializedName("parent_set_limit") val parentSetLimit: Double?,
    @SerializedName("top_anomaly") val topAnomaly: AnomalyInfo?,
    @SerializedName("latest_signals") val latestSignals: SignalAvailability?
)

// Which of the three signals were actually captured for the latest scored session.
// null fields mean "unknown" (legacy prediction); false means "not captured for this
// game" (e.g. no in-game text chat, or a silent session) — distinct from a clean 0%.
data class SignalAvailability(
    val behavior: Boolean?,
    val chat: Boolean?,
    val voice: Boolean?
)

data class Alert(
    val id: Int,
    val type: String,
    val message: String,
    val severity: String,
    @SerializedName("created_at") val createdAt: String,
    val read: Boolean
)

data class TrendPoint(
    val date: String,
    val score: Double,
    val label: String
)

data class DailyHoursPoint(
    val date: String,
    val day: String,
    val hours: Double
)

data class TopGame(
    val game: String,
    val hours: Double,
    val sessions: Int
)

data class HealthResponse(
    val status: String,
    @SerializedName("models_loaded") val modelsLoaded: Boolean
)

data class AlertsResponse(
    val success: Boolean,
    val alerts: List<Alert>?,
    @SerializedName("unread_count") val unreadCount: Int
)

data class MarkReadRequest(
    @SerializedName("alert_ids") val alertIds: List<Int>
)

data class GenericResponse(
    val success: Boolean,
    val message: String?
)

data class SessionSummary(
    val id: Int,
    @SerializedName("game_name") val gameName: String,
    @SerializedName("risk_label") val riskLabel: String,
    @SerializedName("risk_score") val riskScore: Double,
    val duration: String,
    @SerializedName("created_at") val createdAt: String
)

data class ChildStatusResponse(
    val success: Boolean,
    @SerializedName("is_playing") val isPlaying: Boolean,
    @SerializedName("current_game") val currentGame: String?,
    @SerializedName("session_duration_mins") val sessionDurationMins: Int?,
    @SerializedName("current_risk") val currentRisk: String?,
    @SerializedName("risk_score") val riskScore: Double?
)

data class PairResponse(
    val success: Boolean,
    @SerializedName("child_name") val childName: String?,
    @SerializedName("child_user_id") val childUserId: Int?,
    val message: String?
)

// ── Dedicated emotion-insights dashboard ──────────────────────────
data class EmotionCount(
    val emotion: String?,
    val n: Int,
    @SerializedName("avg_intensity") val avgIntensity: Double?
)
data class EmotionRecentSession(
    @SerializedName("game_name") val gameName: String?,
    @SerializedName("start_time") val startTime: String?,
    @SerializedName("dominant_emotion") val dominantEmotion: String?
)
data class EmotionDashboard(
    val success: Boolean,
    @SerializedName("emotion_distribution") val emotionDistribution: List<EmotionCount>?,
    @SerializedName("recent_sessions") val recentSessions: List<EmotionRecentSession>?
)

// ── Dedicated chat-analysis dashboard ─────────────────────────────
data class ChatStats(
    @SerializedName("total_messages") val totalMessages: Int?,
    @SerializedName("avg_toxicity") val avgToxicity: Double?
)
data class ToxicityDistribution(
    val high: Int,
    val medium: Int,
    val safe: Int
)
data class ChatMessageSample(
    val message: String?,
    val confidence: Double?,
    val timestamp: String?,
    @SerializedName("game_name") val gameName: String?
)
data class ChatAnalysisDashboard(
    val success: Boolean,
    val stats: ChatStats?,
    @SerializedName("toxicity_distribution") val toxicityDistribution: ToxicityDistribution?,
    @SerializedName("recent_messages") val recentMessages: List<ChatMessageSample>?
)
