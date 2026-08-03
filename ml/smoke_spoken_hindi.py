# -*- coding: utf-8 -*-
"""Offline feasibility test of the SPOKEN-HINDI chain the paper names as future
work: spoken Hindi -> Vosk Hindi STT (vosk-model-small-hi-0.22, the exact model a
device-side swap would ship) -> Devanagari transcript -> served chat pipeline
(dual-script model + lexicon, noisy-OR).

Audio is synthesized (gTTS studio-clean speech), so this is a CHAIN smoke test —
it measures whether the Hindi recogniser produces transcripts the served pipeline
can score, NOT field performance on child/phone-mic audio.

Requirements: pip install vosk gtts; ffmpeg on PATH; internet (gTTS synthesis);
vosk-model-small-hi-0.22 downloaded from alphacephei.com/vosk/models into
data/voice_models/ (or point VOSK_HI_DIR at its parent directory).

Measured 2026-08-04: 6/6 abuse terms transcribed verbatim; abusive utterances
scored 0.73-0.95 (all clear the 0.6 streak bar; none the 0.95 per-message alert),
clean controls 0.17-0.61 — incl. the finding that clean Devanagari sits slightly
prior-elevated (HASOC 53% offensive base rate), the calibration item to fix
before any device rollout.
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.environ.get('VOSK_HI_DIR', os.path.join(ROOT, 'data', 'voice_models'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
sys.path.insert(0, os.path.join(ROOT, 'ml'))
from text_utils import clean_text, keyword_toxicity
import pickle

PHRASES = [
    # abusive (contain lexicon/model vocabulary)               expected
    ('तू चूतिया है यार',                                        'abusive'),
    ('साले मादरचोद खेलना सीख',                                  'abusive'),
    ('रंडी की तरह मत खेल',                                      'abusive'),
    ('तेरी बहन की भोसड़ीके',                                     'abusive'),
    ('हरामखोर वापस आ जा',                                       'abusive'),
    ('अबे गांडू कहाँ जा रहा है',                                 'abusive'),
    # clean controls
    ('आज मौसम बहुत अच्छा है',                                    'clean'),
    ('चलो एक और गेम खेलते हैं',                                  'clean'),
    ('तुम बहुत अच्छा खेल रहे हो',                                'clean'),
    ('कल स्कूल जाना है',                                        'clean'),
]

from gtts import gTTS
from vosk import Model, KaldiRecognizer

model = Model(os.path.join(SCRATCH, 'vosk-model-small-hi-0.22'))

def load_pkl(name):
    with open(os.path.join(ROOT, 'backend', 'models', name), 'rb') as f:
        return pickle.load(f)

cal, vec = load_pkl('chat_calibrated.pkl'), load_pkl('tfidf_vectorizer.pkl')

def served_score(text):
    ml = cal.predict_proba(vec.transform([clean_text(text)]))[0, 1]
    kw = keyword_toxicity(text)
    return 1.0 - (1.0 - ml) * (1.0 - kw)

results = []
for i, (phrase, expected) in enumerate(PHRASES):
    mp3 = os.path.join(SCRATCH, f'hi_{i}.mp3')
    wav = os.path.join(SCRATCH, f'hi_{i}.wav')
    gTTS(phrase, lang='hi').save(mp3)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'quiet', '-i', mp3,
                    '-ar', '16000', '-ac', '1', '-f', 'wav', wav], check=True)
    rec = KaldiRecognizer(model, 16000)
    with wave.open(wav, 'rb') as wf:
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)
    transcript = json.loads(rec.FinalResult()).get('text', '')
    score = float(served_score(transcript)) if transcript else 0.0
    alert = score >= 0.95
    results.append({'phrase': phrase, 'expected': expected,
                    'transcript': transcript, 'served_score': round(score, 3),
                    'alert': alert})
    print(f"[{expected:7s}] '{phrase}' -> '{transcript}' -> {score:.3f}"
          f"{' ALERT' if alert else ''}", flush=True)
    os.remove(mp3); os.remove(wav)

ab = [r for r in results if r['expected'] == 'abusive']
cl = [r for r in results if r['expected'] == 'clean']
summary = {
    'chain': 'gTTS Hindi -> vosk-model-small-hi-0.22 -> served dual-script pipeline',
    'abusive_alerted': f"{sum(r['alert'] for r in ab)}/{len(ab)}",
    'clean_false_alarms': f"{sum(r['alert'] for r in cl)}/{len(cl)}",
    'results': results,
}
print(json.dumps({k: v for k, v in summary.items() if k != 'results'}, indent=2))
with open(os.path.join(SCRATCH, 'spoken_hindi_chain.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print('[OK] wrote spoken_hindi_chain.json')
