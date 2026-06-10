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
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.pes.gamingdetector.R
import com.pes.gamingdetector.api.ApiClient
import com.pes.gamingdetector.util.Constants
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.DataOutputStream
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.ZipInputStream

class VoiceRecorderService : Service() {
    private var sessionId: Int = -1
    private var serverUrl: String = Constants.BASE_URL
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    // Guards against a duplicate onStartCommand opening a SECOND AudioRecord on the same
    // mic (two recorders contend and one fails / yields garbage).
    @Volatile private var recording = false

    // Vosk requires 16kHz; librosa tone analysis works fine at 16kHz too
    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat) * 2

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        sessionId = intent?.getIntExtra("session_id", -1) ?: -1
        serverUrl = intent?.getStringExtra("server_url") ?: Constants.BASE_URL

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
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
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

        // Already capturing — a repeat start (GameMonitorService re-invoking us) must not
        // open a second recorder on the mic. The flag is cleared when the loop exits for
        // ANY reason (mic busy, model failure), so a later session can try again.
        if (recording) return START_NOT_STICKY
        recording = true
        scope.launch {
            try { recordLoop() } finally { recording = false }
        }
        return START_NOT_STICKY
    }

    private suspend fun recordLoop() {
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
        var segmentStart = System.currentTimeMillis()

        try {
            while (currentCoroutineContext().isActive) {
                val read = recorder.read(chunkBuffer, 0, chunkBuffer.size)
                if (read <= 0) continue

                // Feed to Vosk recognizer for real-time STT
                if (recognizer != null) {
                    if (recognizer.acceptWaveForm(chunkBuffer, read)) {
                        val text = JSONObject(recognizer.result).optString("text").trim()
                        if (text.isNotBlank()) {
                            submitChat(text)
                        }
                    }
                }

                // Accumulate PCM bytes (little-endian) for periodic tone analysis upload
                for (i in 0 until read) {
                    val s = chunkBuffer[i].toInt()
                    pcmAccumulator.write(s and 0xff)
                    pcmAccumulator.write((s shr 8) and 0xff)
                }

                if (System.currentTimeMillis() - segmentStart >= Constants.VOICE_SEGMENT_DURATION_MS) {
                    val pcmCopy = pcmAccumulator.toByteArray()
                    pcmAccumulator.reset()
                    segmentStart = System.currentTimeMillis()
                    if (pcmCopy.isNotEmpty()) {
                        scope.launch { uploadPcmAsWav(pcmCopy) }
                    }
                }
            }

            // Flush any final partial utterance
            recognizer?.let {
                val text = JSONObject(it.finalResult).optString("text").trim()
                if (text.isNotBlank()) submitChat(text)
            }
        } finally {
            recognizer?.close()
            model?.close()
            try { recorder.stop() } catch (_: Exception) {}
            recorder.release()
        }
    }

    private fun loadVoskModel(): Model? {
        return try {
            val modelDir = File(filesDir, "vosk_model")
            if (!modelDir.exists() || modelDir.list().isNullOrEmpty()) {
                extractModelZip(modelDir)
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

    private fun submitChat(text: String) {
        if (sessionId == -1) return
        scope.launch {
            try {
                val api = ApiClient.getInstance(serverUrl)
                api.uploadChat(sessionId, mapOf("message" to text, "source" to "voice_stt"))
            } catch (_: Exception) {
                // Offline — queue the transcript line for retry.
                com.pes.gamingdetector.util.ChatUploadQueue
                    .enqueue(this@VoiceRecorderService, sessionId, text, "voice_stt")
            }
        }
    }

    private suspend fun uploadPcmAsWav(pcmData: ByteArray) {
        val wavFile = File(cacheDir, "voice_${System.currentTimeMillis()}.wav")
        try {
            writePcmToWav(pcmData, wavFile)
            val api = ApiClient.getInstance(serverUrl)
            val requestBody = wavFile.asRequestBody("audio/wav".toMediaType())
            val part = MultipartBody.Part.createFormData("audio", wavFile.name, requestBody)
            api.uploadVoice(sessionId, part)
        } catch (_: Exception) {
        } finally {
            wavFile.delete()
        }
    }

    private fun writePcmToWav(pcmData: ByteArray, wav: File) {
        // All WAV header fields are Little-Endian
        val buf = ByteBuffer.allocate(44 + pcmData.size).order(ByteOrder.LITTLE_ENDIAN)
        buf.put("RIFF".toByteArray())
        buf.putInt(36 + pcmData.size)   // chunk size
        buf.put("WAVEfmt ".toByteArray())
        buf.putInt(16)                  // subchunk1 size
        buf.putShort(1)                 // PCM format
        buf.putShort(1)                 // mono
        buf.putInt(sampleRate)
        buf.putInt(sampleRate * 2)      // byte rate = sampleRate * channels * bitsPerSample/8
        buf.putShort(2)                 // block align = channels * bitsPerSample/8
        buf.putShort(16)                // bits per sample
        buf.put("data".toByteArray())
        buf.putInt(pcmData.size)
        buf.put(pcmData)
        FileOutputStream(wav).use { it.write(buf.array()) }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
