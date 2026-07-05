package com.pes.gamingdetector.util

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Network-aware retry for the offline chat queue.
 *
 * The monitor's poll loop already flushes the queue every ~12 s — but that loop dies
 * with the service, so a line captured offline right before the process is killed only
 * got retried if the service happened to come back. WorkManager persists the request
 * across process death and fires it when connectivity returns, closing that gap.
 * The poll-loop flush stays as the low-latency path; this is the durable one.
 */
class ChatFlushWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return try {
            ChatUploadQueue.flush(applicationContext)
            if (ChatUploadQueue.pendingCount(applicationContext) == 0) Result.success()
            else Result.retry()   // still offline / server throttling — back off and retry
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_NAME = "chat_queue_flush"

        /** Schedule a flush for when the network is next available. KEEP: if one is
         *  already pending, the new line simply rides along with it. */
        fun schedule(context: Context) {
            try {
                val req = OneTimeWorkRequestBuilder<ChatFlushWorker>()
                    .setConstraints(
                        Constraints.Builder()
                            .setRequiredNetworkType(NetworkType.CONNECTED)
                            .build()
                    )
                    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                    .build()
                WorkManager.getInstance(context)
                    .enqueueUniqueWork(UNIQUE_NAME, ExistingWorkPolicy.KEEP, req)
            } catch (_: Exception) {
                // WorkManager unavailable — the poll-loop flush still covers retries.
            }
        }
    }
}
