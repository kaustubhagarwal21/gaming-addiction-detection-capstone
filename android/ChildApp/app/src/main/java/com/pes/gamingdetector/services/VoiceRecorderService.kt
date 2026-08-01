package com.pes.gamingdetector.services

import android.Manifest
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.Constants
import com.pes.gamingdetector.util.PrefsManager
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipInputStream

class VoiceRecorderService : Service() {
    private var sessionId: Int = -1
    private var serverUrl: String = Constants.BASE_URL
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PrefsManager
    private var recordingJob: Job? = null
    private var uploadJob: Job? = null
    // Guards against a duplicate onStartCommand opening a SECOND AudioRecord on the same
    // mic (two recorders contend and one fails / yields garbage).
    @Volatile private var recording = false
    @Volatile private var gracefulStopRequested = false

    // Vosk requires 16kHz; librosa tone analysis works fine at 16kHz too
    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize: Int by lazy {
        val minimum = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        // The API returns negative error codes on unsupported/broken devices. Never
        // pass one to ShortArray/AudioRecord; one second of mono PCM is a safe fallback.
        if (minimum > 0) maxOf(minimum * 2, sampleRate) else sampleRate * 2
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        prefs = PrefsManager(this)
        if (intent?.action == ACTION_STOP) {
            requestGracefulStop(startId)
            return START_NOT_STICKY
        }
        val requestedSession = intent?.getIntExtra("session_id", -1) ?: -1
        val requestedUrl = intent?.getStringExtra("server_url") ?: prefs.serverUrl
        if (!prefs.canMonitor() || requestedSession <= 0 ||
            requestedSession != prefs.activeSessionId) {
            prefs.voiceCaptureActive = false
            stopSelf(startId)
            return START_NOT_STICKY
        }
        // Never mutate identifiers underneath an existing recorder. Otherwise an old
        // PCM/STT job can be silently attributed to a newly started session.
        if (recording) return START_NOT_STICKY
        sessionId = requestedSession
        serverUrl = requestedUrl
        prefs.voiceCaptureActive = false

        // Can't capture audio without the runtime mic permission — bail cleanly.
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            Log.w("VoiceRecorder", "RECORD_AUDIO not granted — skipping voice capture")
            stopSelf()
            return START_NOT_STICKY
        }

        val notif = NotificationCompat.Builder(this, Constants.CHANNEL_MONITORING)
            .setContentTitle("Voice Analysis Active")
            .setSmallIcon(R.drawable.ic_mic)
            .setOngoing(true)
            .build()

        // Android 14+ blocks STARTING a microphone foreground service from the
        // background (the game is foreground, not us). A denial throws here — catch
        // it and degrade gracefully (skip voice for this session) instead of crashing
        // the whole app with an unhandled SecurityException.
        try {
            // FOREGROUND_SERVICE_TYPE_MICROPHONE exists only from API 30 (R). Passing it
            // on Android 10 (Q) throws at startForeground — the catch below then silently
            // dropped voice for the whole session on those devices.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                startForeground(Constants.NOTIF_MONITORING + 10, notif,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
            } else {
                startForeground(Constants.NOTIF_MONITORING + 10, notif)
            }
        } catch (e: Exception) {
            Log.w("VoiceRecorder", "Mic foreground service blocked (likely background-start on Android 14+): ${e.message}")
            stopSelf()
            return START_NOT_STICKY
        }

        recording = true
        gracefulStopRequested = false
        val captureSession = sessionId
        val captureUrl = serverUrl
        recordingJob = scope.launch {
            var session = captureSession
            var url = captureUrl
            try {
                while (true) {
                    try {
                        recordLoop(session, url)
                    } catch (e: Exception) {
                        Log.w("VoiceRecorder", "Voice capture stopped unexpectedly: ${e.message}")
                    }
                    // HANDOVER. Switching straight from one game to another ends session A
                    // and starts B immediately; B's onStartCommand is ignored while this
                    // job is still draining A (see the `recording` guard above), so the
                    // old code then called stopSelf() and B recorded nothing at all.
                    // Pick the new session up here instead of exiting.
                    val next = prefs.activeSessionId
                    if (next > 0 && next != session && prefs.canMonitor()) {
                        Log.i("VoiceRecorder", "handing recorder over to session $next")
                        session = next
                        url = prefs.serverUrl
                        sessionId = next
                        gracefulStopRequested = false
                        continue
                    }
                    break
                }
            } finally {
                recording = false
                prefs.voiceCaptureActive = false
                // Do not leave a foreground "Voice Analysis Active" notification after
                // the recorder failed or exited.
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private suspend fun recordLoop(captureSession: Int, captureUrl: String) {
        val model = withContext(Dispatchers.IO) { loadVoskModel() }
        val recognizer = model?.let {
            try { Recognizer(it, sampleRate.toFloat()) } catch (_: Exception) { null }
        }

        val recorder = try {
            AudioRecord(MediaRecorder.AudioSource.MIC, sampleRate, channelConfig, audioFormat, bufferSize)
        } catch (_: SecurityException) {
            recognizer?.close()
            model?.close()
            return
        }

        // The mic can be unavailable (held by the game / another app) — AudioRecord then
        // stays UNINITIALIZED and startRecording() throws IllegalStateException. Degrade
        // gracefully (no voice this session) instead of crashing the whole app from an
        // unhandled coroutine exception.
        try {
            if (recorder.state != AudioRecord.STATE_INITIALIZED) throw IllegalStateException("AudioRecord not initialized")
            recorder.startRecording()
            prefs.voiceCaptureActive = true
        } catch (e: Exception) {
            Log.w("VoiceRecorder", "Could not start recording (mic busy?): ${e.message}")
            recognizer?.close()
            model?.close()
            recorder.release()
            return
        }

        val chunkBuffer = ShortArray(bufferSize / 2)
        // Raw byte stream, not MutableList<Byte> — a 10s segment is ~320 KB, and boxing
        // every byte cost ~16x that in allocations/GC churn on the audio hot path.
        val pcmAccumulator = java.io.ByteArrayOutputStream()
        var segmentStartElapsed = SystemClock.elapsedRealtime()
        var finalPcm = ByteArray(0)

        try {
            while (currentCoroutineContext().isActive && !gracefulStopRequested) {
                val read = recorder.read(chunkBuffer, 0, chunkBuffer.size)
                if (read < 0) {
                    // Persistent error (ERROR_INVALID_OPERATION etc. — mic revoked or
                    // claimed by another app mid-session). `continue` here hot-spun the
                    // loop at 100% CPU until session end; stop capturing instead.
                    // MUST stay ahead of the foreground gate below: read() does not block
                    // when it is failing, so skipping this check would spin at 100% CPU
                    // exactly while the child is in another app.
                    Log.w("VoiceRecorder", "AudioRecord.read error $read — stopping voice capture")
                    break
                }
                // PRIVACY GATE. A session deliberately stays open for a grace period
                // after the game leaves the foreground (20s normally, 120s for an
                // ancillary flow, and indefinitely while an end request keeps failing).
                // Without this check the microphone kept capturing through all of it, so
                // a conversation held in another app could be recorded, transcribed and
                // attributed to the game. Keep draining the buffer (so AudioRecord stays
                // healthy and does not overflow) but DISCARD everything while the tracked
                // game is not the foreground app, and drop any partially accumulated
                // segment so it cannot be uploaded later.
                if (!trackedGameInForeground()) {
                    if (pcmAccumulator.size() > 0) pcmAccumulator.reset()
                    segmentStartElapsed = SystemClock.elapsedRealtime()
                    continue
                }
                if (read == 0) continue

                // Feed to Vosk recognizer for real-time STT
                if (recognizer != null) {
                    if (recognizer.acceptWaveForm(chunkBuffer, read)) {
                        val text = JSONObject(recognizer.result).optString("text").trim()
                        if (text.isNotBlank()) {
                            submitChat(captureSession, captureUrl, text)
                        }
                    }
                }

                // Accumulate PCM bytes (little-endian) for periodic tone analysis upload
                for (i in 0 until read) {
                    val s = chunkBuffer[i].toInt()
                    pcmAccumulator.write(s and 0xff)
                    pcmAccumulator.write((s shr 8) and 0xff)
                }

                if (SystemClock.elapsedRealtime() - segmentStartElapsed >=
                    Constants.VOICE_SEGMENT_DURATION_MS) {
                    val pcmCopy = pcmAccumulator.toByteArray()
                    pcmAccumulator.reset()
                    segmentStartElapsed = SystemClock.elapsedRealtime()
                    if (pcmCopy.isNotEmpty()) {
                        // Bound the network queue to one request. A 90-second cloud wake
                        // must not accumulate nine WAV uploads/jobs in memory.
                        if (uploadJob?.isActive != true) {
                            uploadJob = scope.launch {
                                uploadPcmAsWav(captureSession, captureUrl, pcmCopy)
                            }
                        } else {
                            Log.w("VoiceRecorder",
                                "Dropping voice segment while prior upload is in flight")
                        }
                    }
                }
            }

            // Flush any final partial utterance
            recognizer?.let {
                val text = JSONObject(it.finalResult).optString("text").trim()
                if (text.isNotBlank()) submitChat(captureSession, captureUrl, text)
            }
            finalPcm = pcmAccumulator.toByteArray()
        } finally {
            recognizer?.close()
            model?.close()
            try { recorder.stop() } catch (_: Exception) {}
            recorder.release()
        }

        // Session-end STOP is graceful: let the one bounded in-flight upload finish,
        // then submit the last partial segment. A hard service/process kill still cancels
        // promptly, and this drain itself is capped so shutdown cannot hang indefinitely.
        withTimeoutOrNull(GRACEFUL_DRAIN_MS) {
            uploadJob?.join()
            if (finalPcm.isNotEmpty()) {
                uploadPcmAsWav(captureSession, captureUrl, finalPcm)
            }
        }
    }

    companion object {
        const val ACTION_STOP = "com.pes.gamingdetector.STOP_VOICE"
        private const val GRACEFUL_DRAIN_MS = 8_000L

        // Bump when assets/vosk_model.zip changes. Without this marker an app UPDATE
        // kept serving the previously-extracted model forever (extraction only ran
        // when the dir was missing), silently ignoring a bundled model swap — e.g.
        // the en-us -> Indian-English (en-in) change for Hinglish-speaking users.
        private const val VOSK_MODEL_VERSION = "small-en-in-0.4"
    }

    /** True only while the exact game this session belongs to is the foreground app.
     *  Fails CLOSED: if the foreground cannot be determined (usage access revoked
     *  mid-session, resolver error), we stop capturing rather than record blind. */
    private fun trackedGameInForeground(): Boolean {
        if (!::prefs.isInitialized || !prefs.canMonitor()) return false
        val tracked = prefs.activeSessionPackage
        if (tracked.isBlank()) {
            // Legacy sessions predate the stored package. Fall back to "a session for
            // this recorder is still active", which is the old behaviour.
            return prefs.activeSessionId == sessionId
        }
        return com.pes.gamingdetector.util.CaptureTargetLogic.isExactSessionTarget(
            tracked, com.pes.gamingdetector.util.ForegroundResolver.current(this))
    }

    private fun requestGracefulStop(startId: Int) {
        gracefulStopRequested = true
        if (recordingJob?.isActive != true) {
            stopSelf(startId)
            return
        }
        // AudioRecord.read is blocking but normally returns within a buffer interval.
        // Force a hard stop shortly after the upload-drain budget if a device driver hangs.
        scope.launch {
            delay(GRACEFUL_DRAIN_MS + 2_000L)
            if (recordingJob?.isActive == true) stopSelf(startId)
        }
    }

    private fun loadVoskModel(): Model? {
        return try {
            val modelDir = File(filesDir, "vosk_model")
            val marker = File(modelDir, ".model_version")
            val stale = !marker.exists() || marker.readText().trim() != VOSK_MODEL_VERSION
            if (stale && modelDir.exists()) modelDir.deleteRecursively()
            if (!modelDir.exists() || modelDir.list().isNullOrEmpty()) {
                extractModelZip(modelDir)
                if (modelDir.exists()) marker.writeText(VOSK_MODEL_VERSION)
            }
            if (modelDir.exists() && !modelDir.list().isNullOrEmpty()) {
                Model(modelDir.absolutePath)
            } else null
        } catch (_: Exception) { null }
    }

    // Extracts assets/vosk_model.zip, stripping the top-level directory prefix,
    // so that filesDir/vosk_model/am/, /conf/, /graph/ etc. are created directly.
    private fun extractModelZip(destDir: File) {
        val zipStream = try {
            assets.open("vosk_model.zip")
        } catch (_: Exception) {
            return  // zip not bundled — STT disabled, tone analysis still runs
        }
        destDir.mkdirs()
        ZipInputStream(zipStream).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val relative = entry.name.substringAfter("/")
                if (relative.isNotEmpty()) {
                    val target = File(destDir, relative)
                    if (entry.isDirectory) {
                        target.mkdirs()
                    } else {
                        target.parentFile?.mkdirs()
                        FileOutputStream(target).use { out -> zis.copyTo(out) }
                    }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    private fun submitChat(captureSession: Int, captureUrl: String, text: String) {
        if (captureSession <= 0) return
        scope.launch {
            try {
                val api = ApiClient.getInstance(captureUrl)
                val resp = api.uploadChat(
                    captureSession, mapOf("message" to text, "source" to "voice_stt"))
                // Retrofit doesn't throw on HTTP errors; queue the transient codes flush()
                // would retry so a 5xx/429 doesn't silently drop the transcript line.
                if (com.pes.gamingdetector.util.ChatQueueLogic.isTransientFailure(resp.code()))
                    com.pes.gamingdetector.util.ChatUploadQueue
                        .enqueue(this@VoiceRecorderService, captureSession, text, "voice_stt")
            } catch (_: Exception) {
                // Network failure — queue the transcript line for retry.
                com.pes.gamingdetector.util.ChatUploadQueue
                    .enqueue(this@VoiceRecorderService, captureSession, text, "voice_stt")
            }
        }
    }

    private suspend fun uploadPcmAsWav(
        captureSession: Int,
        captureUrl: String,
        pcmData: ByteArray
    ) {
        val wavFile = File(cacheDir, "voice_${System.currentTimeMillis()}.wav")
        try {
            writePcmToWav(pcmData, wavFile)
            val api = ApiClient.getInstance(captureUrl)
            val requestBody = wavFile.asRequestBody("audio/wav".toMediaType())
            val part = MultipartBody.Part.createFormData("audio", wavFile.name, requestBody)
            var delivered = false
            repeat(2) { attempt ->
                if (delivered) return@repeat
                try {
                    val response = api.uploadVoice(captureSession, part)
                    val retryable = response.code() == 408 || response.code() == 429 ||
                        response.code() >= 500
                    delivered = response.isSuccessful && response.body()?.success == true
                    if (!delivered && retryable && attempt == 0) delay(1_000)
                } catch (_: java.io.IOException) {
                    if (attempt == 0) delay(1_000)
                }
            }
            // This represents the working end-to-end voice path, not just permission.
            // A VAD-rejected but successfully handled clip is still a healthy pipeline.
            prefs.voiceCaptureActive = delivered
            if (!delivered) Log.w("VoiceRecorder", "Voice upload failed after retry")
        } catch (e: Exception) {
            prefs.voiceCaptureActive = false
            Log.w("VoiceRecorder", "Voice upload failed: ${e.message}")
        } finally {
            wavFile.delete()
        }
    }

    private fun writePcmToWav(pcmData: ByteArray, wav: File) {
        // Header maths lives in WavUtil (pure, JVM-unit-tested).
        FileOutputStream(wav).use { it.write(com.pes.gamingdetector.util.WavUtil.pcmToWav(pcmData, sampleRate)) }
    }

    override fun onDestroy() {
        if (::prefs.isInitialized) prefs.voiceCaptureActive = false
        gracefulStopRequested = true
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
