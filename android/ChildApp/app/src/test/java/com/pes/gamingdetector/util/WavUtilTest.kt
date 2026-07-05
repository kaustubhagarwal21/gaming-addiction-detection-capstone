package com.pes.gamingdetector.util

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * The WAV container the child app uploads. The backend's librosa/soundfile loader
 * rejects a malformed header outright — a single wrong field silently kills the whole
 * voice channel, so every header field is pinned here.
 */
class WavUtilTest {

    private val sampleRate = 16000

    private fun header(pcm: ByteArray): ByteBuffer =
        ByteBuffer.wrap(WavUtil.pcmToWav(pcm, sampleRate)).order(ByteOrder.LITTLE_ENDIAN)

    private fun ascii(buf: ByteBuffer, at: Int, len: Int): String {
        val b = ByteArray(len)
        for (i in 0 until len) b[i] = buf.get(at + i)
        return String(b, Charsets.US_ASCII)
    }

    @Test
    fun `output is exactly 44 header bytes plus the pcm payload`() {
        val pcm = ByteArray(320) { it.toByte() }
        assertEquals(44 + pcm.size, WavUtil.pcmToWav(pcm, sampleRate).size)
    }

    @Test
    fun `riff wave fmt and data magics are at the canonical offsets`() {
        val buf = header(ByteArray(4))
        assertEquals("RIFF", ascii(buf, 0, 4))
        assertEquals("WAVE", ascii(buf, 8, 4))
        assertEquals("fmt ", ascii(buf, 12, 4))
        assertEquals("data", ascii(buf, 36, 4))
    }

    @Test
    fun `chunk sizes match the payload`() {
        val pcm = ByteArray(1000)
        val buf = header(pcm)
        assertEquals(36 + pcm.size, buf.getInt(4))    // RIFF chunk size
        assertEquals(16, buf.getInt(16))              // fmt subchunk size
        assertEquals(pcm.size, buf.getInt(40))        // data length
    }

    @Test
    fun `format fields describe 16-bit mono pcm at the recorder's rate`() {
        val buf = header(ByteArray(2))
        assertEquals(1, buf.getShort(20).toInt())              // PCM
        assertEquals(1, buf.getShort(22).toInt())              // mono
        assertEquals(sampleRate, buf.getInt(24))
        assertEquals(sampleRate * 2, buf.getInt(28))           // byte rate
        assertEquals(2, buf.getShort(32).toInt())              // block align
        assertEquals(16, buf.getShort(34).toInt())             // bits per sample
    }

    @Test
    fun `pcm payload is carried through byte-for-byte`() {
        val pcm = ByteArray(256) { (it * 7).toByte() }
        val out = WavUtil.pcmToWav(pcm, sampleRate)
        assertArrayEquals(pcm, out.copyOfRange(44, out.size))
    }

    @Test
    fun `empty segment still yields a valid 44-byte container`() {
        val out = WavUtil.pcmToWav(ByteArray(0), sampleRate)
        assertEquals(44, out.size)
        val buf = ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(36, buf.getInt(4))
        assertEquals(0, buf.getInt(40))
    }
}
