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
 * Network-aware retry for the offline chat and session queues.
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
        // Clear BEFORE reading the queues: a line enqueued while this pass runs must be
        // able to append one fresh pass of its own (see schedule()).
        passScheduled.set(false)
        return try {
            ChatUploadQueue.flush(applicationContext)
            OfflineSessionBuffer.flush(applicationContext)
            if (ChatUploadQueue.pendingCount(applicationContext) == 0 &&
                OfflineSessionBuffer.pendingCount(applicationContext) == 0) Result.success()
            else Result.retry()   // still offline / server throttling — back off and retry
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_NAME = "chat_queue_flush"

        // At most ONE outstanding appended pass. enqueue()/record() commit the line to
        // disk BEFORE calling schedule(), so any pass that STARTS afterwards will see
        // it — appending on EVERY enqueue (the old behaviour) grew the unique chain by
        // one no-op worker per line captured offline; a burst of offline typing queued
        // dozens. Process death loses the flag but not the persisted chain; the next
        // enqueue then appends at most one extra pass.
        private val passScheduled = java.util.concurrent.atomic.AtomicBoolean(false)

        /** Schedule a flush for when the network is next available. APPEND_OR_REPLACE:
     *  if one is already running, append one final pass so an enqueue racing with that
     *  worker's last pending-count check cannot be stranded without durable work. */
        fun schedule(context: Context) {
            if (!passScheduled.compareAndSet(false, true)) return
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
                    .enqueueUniqueWork(
                        UNIQUE_NAME,
                        ExistingWorkPolicy.APPEND_OR_REPLACE,
                        req
                    )
            } catch (_: Exception) {
                // WorkManager unavailable — the poll-loop flush still covers retries.
                // Release the marker so a later enqueue can try scheduling again.
                passScheduled.set(false)
            }
        }
    }
}
