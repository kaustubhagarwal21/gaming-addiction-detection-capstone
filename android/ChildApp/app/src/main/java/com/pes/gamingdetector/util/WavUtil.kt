package com.pes.gamingdetector.util

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Canonical 44-byte PCM WAV encoding (mono, 16-bit). Pure — no Android types — so the
 * header maths is verifiable under plain-JVM unit tests; a wrong chunk size or byte
 * rate makes the backend's feature extractor reject every uploaded segment.
 */
object WavUtil {

    /** Wrap raw 16-bit mono PCM in a WAV container. All header fields Little-Endian. */
    fun pcmToWav(pcmData: ByteArray, sampleRate: Int): ByteArray {
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
        return buf.array()
    }
}
