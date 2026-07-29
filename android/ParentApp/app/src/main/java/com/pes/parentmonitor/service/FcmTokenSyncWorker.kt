package com.pes.parentmonitor.service

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.pes.parentmonitor.api.ApiClient
import com.pes.parentmonitor.util.PrefsManager
import kotlinx.coroutines.CancellationException
import java.util.concurrent.TimeUnit

/** Persists FCM registration changes across Activity/process death and retries them
 * when connectivity returns. Register/unregister operations share one ordered chain,
 * so a quick logout followed by login cannot leave the backend in the wrong state. */
class FcmTokenSyncWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val action = inputData.getString(KEY_ACTION) ?: return Result.failure()
        val token = inputData.getString(KEY_TOKEN)?.takeIf { it.isNotBlank() }
            ?: return Result.failure()

        return try {
            val response = when (action) {
                ACTION_REGISTER -> {
                    val prefs = PrefsManager(applicationContext)
                    // This work may have waited offline while the user logged out or FCM
                    // rotated again. Never register a token for a stale session.
                    if (!prefs.isLoggedIn() || prefs.fcmToken != token) return Result.success()
                    ApiClient.getInstance(prefs.serverUrl).updateFcmToken(
                        mapOf("user_id" to prefs.parentId, "fcm_token" to token)
                    )
                }
                ACTION_UNREGISTER -> {
                    val serverUrl = inputData.getString(KEY_SERVER_URL)
                        ?.takeIf { it.isNotBlank() } ?: return Result.failure()
                    ApiClient.getInstance(serverUrl).unregisterFcmToken(
                        mapOf("fcm_token" to token)
                    )
                }
                else -> return Result.failure()
            }

            when {
                response.isSuccessful && response.body()?.success == true -> Result.success()
                response.code() == 408 || response.code() == 429 || response.code() >= 500 ->
                    retryOrReleaseUnregister(action)
                // Deregistration is best-effort. A permanent error (for example an
                // older backend without this endpoint) must not fail the unique work
                // chain and cancel a later registration for the current login.
                action == ACTION_UNREGISTER -> Result.success()
                else -> Result.failure()
            }
        } catch (_: java.io.IOException) {
            retryOrReleaseUnregister(action)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            if (action == ACTION_UNREGISTER) Result.success() else Result.failure()
        }
    }

    /**
     * Do not let an unreachable old server block a new login's registration forever.
     * Three exponentially backed-off attempts are enough for best-effort cleanup; FCM
     * family binding still prevents stale old-server pushes from being displayed.
     */
    private fun retryOrReleaseUnregister(action: String): Result =
        if (action == ACTION_UNREGISTER && runAttemptCount >= 2) {
            Result.success()
        } else {
            Result.retry()
        }

    companion object {
        private const val UNIQUE_NAME = "parent_fcm_token_sync"
        private const val KEY_ACTION = "action"
        private const val KEY_TOKEN = "token"
        private const val KEY_SERVER_URL = "server_url"
        private const val ACTION_REGISTER = "register"
        private const val ACTION_UNREGISTER = "unregister"

        fun enqueueRegistration(context: Context, token: String) {
            if (token.isBlank()) return
            enqueue(context, Data.Builder()
                .putString(KEY_ACTION, ACTION_REGISTER)
                .putString(KEY_TOKEN, token)
                .build())
        }

        fun enqueueUnregistration(context: Context, serverUrl: String, token: String) {
            if (serverUrl.isBlank() || token.isBlank()) return
            enqueue(context, Data.Builder()
                .putString(KEY_ACTION, ACTION_UNREGISTER)
                .putString(KEY_SERVER_URL, serverUrl)
                .putString(KEY_TOKEN, token)
                .build())
        }

        private fun enqueue(context: Context, data: Data) {
            val request = OneTimeWorkRequestBuilder<FcmTokenSyncWorker>()
                .setInputData(data)
                .setConstraints(Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context.applicationContext)
                .enqueueUniqueWork(UNIQUE_NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }
    }
}
