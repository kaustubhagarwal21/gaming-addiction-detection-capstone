"""Unit tests for the ML plumbing added in the pipeline overhaul: the shared audio
extractor (silence floor, feature shape, gain invariance), the noisy-OR toxicity
fusion, the Hinglish-extended keyword lexicon, the deleted-account token check, and
the feedback threshold-tuner's Beta-posterior math."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml')))


# ─── Shared audio extractor (backend/audio_features.py) ─────────────

def test_silence_floor_rejects_near_silent_clip():
    librosa = pytest.importorskip('librosa')  # noqa: F841
    from audio_features import extract_features_from_array, SAMPLE_RATE
    y = np.zeros(SAMPLE_RATE * 2, dtype=np.float32) + 1e-5
    feats, dur = extract_features_from_array(y, SAMPLE_RATE, apply_vad=False)
    assert feats is None                       # silent → "no voice", never an emotion
    assert dur == pytest.approx(2.0, abs=0.01)


def test_feature_vector_contract():
    """36 features, with the FIRST 17 frozen in order (13 MFCC means, pitch mean/std,
    energy mean/std) — serving slices to the loaded model's n_features_in_, so the
    prefix order is a compatibility contract, not a convention."""
    pytest.importorskip('librosa')
    import librosa
    from audio_features import extract_features_from_array, SAMPLE_RATE
    t = np.linspace(0, 2, SAMPLE_RATE * 2)
    y = (0.1 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    feats, _ = extract_features_from_array(y, SAMPLE_RATE, apply_vad=False)
    assert feats is not None and len(feats) == 36
    # Spot-check the frozen prefix: positions 0-12 are the MFCC MEANS of the
    # gain-normalised clip, position 15 is mean frame-RMS (the normalisation target).
    y_norm = y * (0.045 / np.sqrt(np.mean(y ** 2)))
    mfcc_means = np.mean(librosa.feature.mfcc(y=y_norm, sr=SAMPLE_RATE, n_mfcc=13), axis=1)
    np.testing.assert_allclose(feats[:13], mfcc_means, rtol=1e-4)
    assert feats[15] == pytest.approx(float(np.mean(librosa.feature.rms(y=y_norm)[0])), rel=1e-4)


def test_gain_invariance():
    """The same clip at very different mic gains must produce ~identical features —
    the fixed-RMS normalisation is what makes the energy features meaningful."""
    pytest.importorskip('librosa')
    from audio_features import extract_features_from_array, SAMPLE_RATE
    t = np.linspace(0, 2, SAMPLE_RATE * 2)
    y = (np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
    quiet, _ = extract_features_from_array(0.02 * y, SAMPLE_RATE, apply_vad=False)
    loud, _  = extract_features_from_array(0.50 * y, SAMPLE_RATE, apply_vad=False)
    assert quiet is not None and loud is not None
    np.testing.assert_allclose(quiet, loud, rtol=1e-4, atol=1e-4)


# ─── Noisy-OR toxicity fusion (app.fuse_toxicity) ────────────────────

def test_noisy_or_properties():
    from app import fuse_toxicity
    assert fuse_toxicity(0.0, 0.7) == pytest.approx(0.7)     # single-signal identity
    assert fuse_toxicity(0.6, 0.0) == pytest.approx(0.6)
    assert fuse_toxicity(0.5, 0.5) == pytest.approx(0.75)    # reinforcement > max()
    assert fuse_toxicity(0.5, 0.5) >= max(0.5, 0.5)
    assert 0.0 <= fuse_toxicity(1.0, 1.0) <= 1.0             # stays a probability
    assert fuse_toxicity(-3, 7) == pytest.approx(1.0)        # clipped garbage input


# ─── Keyword lexicon incl. Hinglish (text_utils) ─────────────────────

def test_keyword_toxicity_hinglish_terms():
    from text_utils import keyword_toxicity
    assert keyword_toxicity('madarchod') > 0
    assert keyword_toxicity('bsdk') > 0                      # slang-map expansion
    assert keyword_toxicity('kya chutya hai tu') > 0         # obfuscated variant
    assert keyword_toxicity('tu harami kutta hai') > 0       # medium-tier insults


def test_keyword_toxicity_devanagari_terms():
    """Typed chat arrives verbatim, so Devanagari-script abuse must score — and a
    clean Hindi sentence must not (clean_text keeps Devanagari; \\w is unicode)."""
    from text_utils import keyword_toxicity
    assert keyword_toxicity('मादरचोद') > 0
    assert keyword_toxicity('तू चूतिया है') > 0
    assert keyword_toxicity('अच्छा खेला भाई') == 0.0         # "well played bro"


def test_keyword_toxicity_clean_gaming_chat_stays_zero():
    from text_utils import keyword_toxicity
    for msg in ('nice kill bro', 'gg well played', 'push mid now',
                'i died lol one more game', 'mc server aaja',   # 'mc' = Minecraft, NOT abuse
                'bc of lag i lost'):                            # 'bc' = because
        assert keyword_toxicity(msg) == 0.0, msg


# ─── Deleted-account token check (app._user_exists) ──────────────────

def test_deleted_user_token_denied(client, monkeypatch):
    import app as appmod
    conn = appmod.get_db()
    uid = appmod.insert_returning_id(
        conn, "INSERT INTO users (name, pin, parent_pin, age, family_code) "
              "VALUES ('Ghost','','',15,'GHOST1')", (), pk='user_id')
    conn.commit()
    conn.close()
    token = appmod.mint_token('parent', uid, [uid])

    monkeypatch.setattr(appmod, 'AUTH_ENFORCE', True)
    hdrs = {'Authorization': f'Bearer {token}'}
    r = client.get(f'/api/alerts?user_id={uid}', headers=hdrs)
    assert r.status_code == 200                              # account alive → allowed

    conn = appmod.get_db()
    conn.execute('DELETE FROM users WHERE user_id=?', (uid,))
    conn.commit()
    conn.close()
    appmod._user_exists_cache.pop(uid, None)                 # what account deletion does
    r = client.get(f'/api/alerts?user_id={uid}', headers=hdrs)
    assert r.status_code == 401                              # signed token, dead account


# ─── Robust anomaly z-score (app._mad_z) ─────────────────────────────

def test_mad_z_resists_outlier_masking():
    """A previous huge day must not hide a later spike — the failure mode of
    std-based z (the outlier inflates the denominator) that median/MAD fixes."""
    from app import _mad_z
    history = [2.0] * 25 + [20.0]        # steady ~2 h/day plus one 20 h binge
    assert abs(_mad_z(2.0, history)) < 0.5          # a typical day stays unremarkable
    spike_z = _mad_z(10.0, history)                  # a NEW 10 h day...
    classic_z = (10.0 - np.mean(history)) / np.std(history)
    assert spike_z >= 2.5                            # ...still flags under MAD
    assert classic_z < 2.5                           # ...but was masked under std
    assert _mad_z(2.0, [2.0] * 20) == 0.0            # constant history: floored, not inf


# ─── Feedback threshold tuner (ml/tune_from_feedback.py) ─────────────

# ─── Drift monitor PSI (ml/monitor_drift.py) ─────────────────────────

def test_psi_identical_and_shifted():
    from monitor_drift import psi
    rng = np.random.default_rng(0)
    ref = rng.normal(0.4, 0.15, 2000)
    same = rng.normal(0.4, 0.15, 2000)
    shifted = rng.normal(0.55, 0.15, 2000)
    assert psi(ref, same) < 0.05                 # same distribution → ~0
    assert psi(ref, shifted) > 0.2               # material shift → DRIFT band
    assert psi(ref, ref) < 1e-6                  # exact self-comparison
    assert np.isfinite(psi(np.full(500, 0.5), rng.normal(0.5, 0.1, 500)))  # degenerate ref


def test_drift_population_gate_requires_both_windows():
    from monitor_drift import drift_gate_eligible, finite_mean
    assert drift_gate_eligible(3, 3, 3) is True
    assert drift_gate_eligible(20, 2, 3) is False
    assert drift_gate_eligible(2, 20, 3) is False
    assert finite_mean([None, float('nan')]) is None
    assert finite_mean([0, 1, None]) == pytest.approx(0.5)


def test_fusion_weight_grid_includes_all_boundary_combinations():
    from analyze_fusion_sensitivity import served_band, weight_combos
    combos = weight_combos()
    assert len(combos) == 37
    assert (0.25, 0.30, 0.45) in combos
    assert (0.55, 0.30, 0.15) in combos
    assert (0.40, 0.15, 0.45) in combos
    assert (0.40, 0.45, 0.15) in combos
    assert all(sum(c) == pytest.approx(1.0) for c in combos)
    assert served_band({'observation_cap': True}, 0.9, 0.33, 0.67) == 'at_risk'
    assert served_band({'observation_cap': False}, 0.9, 0.33, 0.67) == 'addicted'


def test_prevalence_threshold_reports_finite_sample_share_and_validates():
    from calibrate_thresholds_prevalence import prevalence_threshold
    scores = np.linspace(0.01, 1.0, 100)
    threshold, achieved = prevalence_threshold(scores, 0.064)
    assert 0.9 < threshold < 1.0
    assert achieved == pytest.approx(0.07)
    with pytest.raises(ValueError):
        prevalence_threshold(scores, 0.0)
    with pytest.raises(ValueError):
        prevalence_threshold([0.2, np.nan], 0.1)


def test_voice_shadow_math_validates_vectors_and_bbse_orientation():
    from analyze_voice_shadow import (CLASSES, abstain_labels, bbse_prior,
                                      probability_vector)
    p = probability_vector('{"angry": 0.1, "excited": 0.1, '
                           '"frustrated": 0.6001, "neutral": 0.1999}')
    assert p is not None and p.sum() == pytest.approx(1.0)
    assert probability_vector('{bad json') is None
    assert probability_vector({'angry': float('nan')}) is None
    P = np.array([[0.1, 0.1, 0.5, 0.3], [0.1, 0.1, 0.2, 0.6]])
    assert abstain_labels(P, 0.1) == ['frustrated', 'neutral']
    q = np.array([0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(bbse_prior(np.eye(4), q), q, atol=1e-6)
    assert len(CLASSES) == 4


def test_chat_sweep_contains_each_served_marker_once():
    from eval_chat_conda import ALERT_HIGH_T, ALERT_T, sweep_thresholds
    thresholds = sweep_thresholds(0.75, ALERT_T)
    assert thresholds == sorted(set(thresholds))
    assert thresholds.count(ALERT_T) == 1
    assert thresholds.count(ALERT_HIGH_T) == 1


def test_posterior_exceeds_monotonic_in_evidence():
    from tune_from_feedback import _posterior_exceeds
    assert _posterior_exceeds(0, 0, 0.4) == 0.0              # no evidence → no claim
    weak   = _posterior_exceeds(2, 3, 0.4)                   # 2/3 false alarms
    strong = _posterior_exceeds(20, 30, 0.4)                 # same rate, 10x evidence
    assert strong > weak > 0.5                               # more data → more certainty


def test_recommend_guards_and_direction():
    from tune_from_feedback import _analyse_group, _recommend
    fa  = [{'label': 'false_alarm'}] * 8 + [{'label': 'accurate'}] * 2
    ev  = _analyse_group(fa)
    new, _ = _recommend(0.67, ev, 'RISK_T2')
    assert new > 0.67                                        # false alarms push the cut UP
    assert new <= 0.67 + 0.05 + 1e-9                         # capped step

    late = [{'label': 'too_late'}] * 8 + [{'label': 'accurate'}] * 2
    new, _ = _recommend(0.67, _analyse_group(late), 'RISK_T2')
    assert new < 0.67                                        # misses push the cut DOWN

    sparse = [{'label': 'false_alarm'}] * 3                  # under MIN_LABELS
    new, why = _recommend(0.67, _analyse_group(sparse), 'RISK_T2')
    assert new == 0.67 and 'unchanged' in why


# ─── Keyword channel vs punctuation (regression) ─────────────────────

def test_keyword_toxicity_survives_punctuation():
    """Typed chat ends words with punctuation; a whitespace-only split silently
    zeroed the keyword channel — the ONLY detector for Hinglish/Devanagari abuse."""
    from text_utils import keyword_toxicity
    assert keyword_toxicity('you are trash!') == keyword_toxicity('you are trash') > 0
    assert keyword_toxicity('bsdk!!') > 0                     # slang → bhosdike (HIGH)
    assert keyword_toxicity('kys!') >= 0.3                    # slang → phrase 'kill yourself'
    assert keyword_toxicity('चूतिया!') > 0                    # Devanagari + punctuation
    assert keyword_toxicity('fuck!!!') > 0                    # repeat-collapse + strip
    assert keyword_toxicity('nice shot, well played') == 0.0  # clean stays clean


def test_tuner_defaults_match_serving():
    """A stale DEFAULTS entry anchors tuner recommendations at the wrong operating
    point (0.75 vs the served 0.90 went unnoticed once already)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    app_src   = (root / 'backend' / 'app.py').read_text(encoding='utf-8')
    tuner_src = (root / 'ml' / 'tune_from_feedback.py').read_text(encoding='utf-8')
    served = {}
    for key in ('RISK_T1', 'RISK_T2', 'CHAT_ALERT_T'):
        match = re.search(
            rf"{key}\s*=\s*_env_float\(\s*'{key}',\s*([\d.]+)",
            app_src,
        )
        assert match, f'could not locate the serving default for {key}'
        served[key] = float(match.group(1))
    tuner = eval(re.search(r'DEFAULTS\s*=\s*(\{[^}]+\})', tuner_src).group(1))
    assert tuner == served, f'tuner DEFAULTS {tuner} != serving defaults {served}'
