"""
Single source of truth for the 36 acoustic voice features:
the frozen 17-prefix (13 MFCC means + pitch mean/std + energy mean/std) followed by
appended v2 features (13 MFCC standard deviations + spectral-centroid, zero-crossing
and rolloff mean/std). New features are APPEND-ONLY: serving slices the vector to the
loaded model's n_features_in_, so older models keep working during rollout.

Imported by BOTH the backend (app.py) and the real-audio trainer
(ml/train_voice_real.py) so the voice model is trained and served on the IDENTICAL
extraction — the same train/serve-alignment discipline text_utils.py (chat) and
behavior_features.py (behaviour) already enforce.

Pipeline, in order:
  1. Silence floor — a near-silent clip is rejected outright: gain normalisation
     would otherwise amplify room/mic noise up to speech level and the model would
     read the noise as an emotion.
  2. Gain normalisation — each clip is scaled to a fixed reference RMS so the energy
     features are microphone-gain-INVARIANT (phone mic gain / distance varies wildly).
  3. Voice-activity detection (webrtcvad, optional) — rejects clips with (almost) no
     actual SPEECH. Game audio, music and background chatter pass an energy floor but
     not a VAD; without this they were gain-boosted and classified as an emotion.
     Active automatically when webrtcvad is installed; disable with VOICE_VAD=0.
  4. Feature extraction — 13 MFCC means, yin pitch mean/std, frame-RMS mean/std.

Env knobs (all optional): VOICE_RMS_TARGET, VOICE_SILENCE_RMS, VOICE_VAD,
VOICE_VAD_MIN_SPEECH, VOICE_VAD_AGGRESSIVENESS, VOICE_DEBUG.
"""
import logging
import os

import numpy as np

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

# Optional — a tiny C extension; extraction degrades gracefully without it.
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False

logger = logging.getLogger(__name__)

SAMPLE_RATE   = 22050   # analysis rate (device uploads 16 kHz WAVs; librosa resamples)
_VAD_SR       = 16000   # webrtcvad accepts 8/16/32/48 kHz only
_VAD_FRAME_MS = 30


def _vad_enabled() -> bool:
    return VAD_AVAILABLE and os.environ.get('VOICE_VAD', '1').lower() not in ('0', 'false', 'no')


def _debug() -> bool:
    return os.environ.get('VOICE_DEBUG', '').lower() in ('1', 'true', 'yes')


def speech_ratio(y: np.ndarray, sr: int) -> float:
    """Fraction of 30 ms frames webrtcvad judges to be speech (0..1)."""
    y16 = librosa.resample(y, orig_sr=sr, target_sr=_VAD_SR) if sr != _VAD_SR else y
    pcm = np.clip(y16 * 32767.0, -32768, 32767).astype(np.int16).tobytes()
    frame_bytes = int(_VAD_SR * _VAD_FRAME_MS / 1000) * 2   # 16-bit mono
    n_frames = len(pcm) // frame_bytes
    if n_frames == 0:
        return 0.0
    # Aggressiveness 3 (strictest). webrtcvad is a speech-tuned GMM, not a noise
    # detector: synthetic broadband noise can still read as "speech" in some sample-rate
    # paths, so this gate targets the PRACTICAL contaminants (music, structured game
    # audio, silence-adjacent murmur), not an adversarial noise generator. Strict is the
    # right default because a wrongly-rejected borderline clip merely degrades to a
    # low-confidence neutral — the safe direction for a screening system.
    vad = webrtcvad.Vad(int(os.environ.get('VOICE_VAD_AGGRESSIVENESS', '3')))
    speech = sum(1 for i in range(n_frames)
                 if vad.is_speech(pcm[i * frame_bytes:(i + 1) * frame_bytes], _VAD_SR))
    return speech / n_frames


def extract_features_from_array(y: np.ndarray, sr: int, apply_vad: bool = True):
    """(features, duration_seconds) from a mono float waveform.

    features is None when the clip is rejected (too short / silent / no speech) or
    extraction fails — callers treat that as "no voice in this segment".
    apply_vad=False lets the trainer skip VAD on curated corpora (every clip is
    known speech) and keeps extraction fast over thousands of files.
    """
    try:
        duration = len(y) / float(sr)
        if len(y) < 512:
            return None, duration

        rms_target = float(os.environ.get('VOICE_RMS_TARGET', '0.045'))
        cur_rms = float(np.sqrt(np.mean(y ** 2)))
        # 1. Silence floor (see module docstring).
        if cur_rms < float(os.environ.get('VOICE_SILENCE_RMS', '0.0015')):
            return None, duration
        # 2. Gain normalisation.
        y = y * (rms_target / cur_rms)

        # 3. VAD gate: reject segments that contain essentially no speech.
        if apply_vad and _vad_enabled():
            try:
                ratio = speech_ratio(y, sr)
                min_ratio = float(os.environ.get('VOICE_VAD_MIN_SPEECH', '0.1'))
                if ratio < min_ratio:
                    if _debug():
                        logger.info(f"[VOICE_DEBUG] VAD reject: speech_ratio={ratio:.2f} < {min_ratio}")
                    return None, duration
                if _debug():
                    logger.info(f"[VOICE_DEBUG] VAD speech_ratio={ratio:.2f}")
            except Exception as e:              # VAD trouble must never kill extraction
                logger.debug(f"VAD skipped: {e}")

        # 4. Features. ORDER CONTRACT: the first 17 values ([13 MFCC means, pitch
        # mean/std, energy mean/std]) are frozen — newer features are APPENDED only,
        # and serving slices the vector to the loaded model's n_features_in_, so an
        # older 17-feature model keeps working during rollout (the same pattern the
        # behaviour channel uses for its feature list).
        mfcc_mat = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc     = np.mean(mfcc_mat, axis=1).tolist()
        try:
            f0     = librosa.yin(y, fmin=50, fmax=500, sr=sr)
            f0v    = f0[f0 > 0]
            p_mean = float(np.mean(f0v)) if len(f0v) > 0 else 0.0
            p_std  = float(np.std(f0v))  if len(f0v) > 0 else 0.0
        except Exception:
            p_mean, p_std = 150.0, 30.0
        rms    = librosa.feature.rms(y=y)[0]
        e_mean = float(np.mean(rms))
        e_std  = float(np.std(rms))

        # Appended (v2) features: emotion lives in VARIABILITY as much as level —
        # an agitated voice wobbles across the spectrum — yet the original vector
        # kept only MFCC means, discarding every variance cue. Add the 13 MFCC
        # standard deviations plus spectral-centroid / zero-crossing / rolloff
        # statistics (brightness and noisiness of the voice), all standard
        # speech-emotion features.
        mfcc_std = np.std(mfcc_mat, axis=1).tolist()
        cent     = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        zcr      = librosa.feature.zero_crossing_rate(y)[0]
        roll     = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        extras   = [float(np.mean(cent)), float(np.std(cent)),
                    float(np.mean(zcr)),  float(np.std(zcr)),
                    float(np.mean(roll)), float(np.std(roll))]

        if _debug():
            logger.info(f"[VOICE_DEBUG] rms_in={cur_rms:.4f} e_mean={e_mean:.4f} e_std={e_std:.4f} "
                        f"p_mean={p_mean:.1f} p_std={p_std:.1f} mfcc0={mfcc[0]:.1f}")

        return (mfcc + [p_mean, p_std, e_mean, e_std] + mfcc_std + extras,
                round(duration, 2))
    except Exception as e:
        logger.error(f"Audio feature error: {e}")
        return None, 0.0


def extract_features(audio_path: str, apply_vad: bool = True):
    """(features, duration_seconds) from an audio file — the serving entry point."""
    if not LIBROSA_AVAILABLE:
        return None, 0.0
    try:
        y, sr = librosa.load(audio_path, sr=SAMPLE_RATE, duration=30)
    except Exception as e:
        logger.error(f"Audio load error ({audio_path}): {e}")
        return None, 0.0
    return extract_features_from_array(y, sr, apply_vad=apply_vad)
