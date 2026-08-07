# -*- coding: utf-8 -*-
"""Three-way STT engine comparison on CODE-MIXED Hinglish speech — the real
target register.

Requires: pip install vosk gtts faster-whisper; ffmpeg on PATH; internet (gTTS);
vosk-model-small-en-in-0.4 and vosk-model-small-hi-0.22 downloaded from
alphacephei.com/vosk/models into data/voice_models/ (or set STT_MODELS_DIR).

Measured 2026-08-04 (docs/stt_shootout.json): whisper-tiny code-switches natively
but transcribed the abuse vocabulary worse than vosk-hi at phone-deployable size,
ran 0.4-1.5 s/clip on a DESKTOP CPU, and hallucinates fluent text on non-speech
audio — the unsafe failure mode for an alerting product. Dual-Vosk retained.

Engines:
  A) vosk-model-small-en-in  (deployed today, English-only)
  B) vosk-model-small-hi     (the candidate swap)
  C) faster-whisper tiny     (ONE multilingual model, code-switch capable —
                              the 'single model' question)
Each transcript is scored by the served dual-script chat pipeline.
Audio = gTTS synthesis (studio-clean); chain smoke test, not field performance.
"""
import json
import os
import subprocess
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Vosk models + gTTS temp files + output live here (downloads noted in docstring).
SCRATCH = os.environ.get('STT_MODELS_DIR', os.path.join(ROOT, 'data', 'voice_models'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
from text_utils import clean_text, keyword_toxicity
import pickle

PHRASES = [
    # code-mixed abusive (the register children actually speak)
    ('अबे चूतिया tune पूरा game बर्बाद कर दिया',            'abusive'),
    ('kill him yaar वो रंडी की तरह भाग रहा है',              'abusive'),
    ('madarchod noob team में मत आना',                       'abusive'),
    ('तू harami है bro uninstall कर दे',                     'abusive'),
    # code-mixed clean
    ('yaar ये level बहुत hard है',                           'clean'),
    ('good game भाई कल फिर खेलते हैं',                       'clean'),
    ('मेरा internet slow चल रहा है',                         'clean'),
]

from gtts import gTTS
from vosk import Model as VoskModel, KaldiRecognizer
from faster_whisper import WhisperModel

def load_pkl(name):
    with open(os.path.join(ROOT, 'backend', 'models', name), 'rb') as f:
        return pickle.load(f)

cal, vec = load_pkl('chat_calibrated.pkl'), load_pkl('tfidf_vectorizer.pkl')

def served_score(text):
    if not text:
        return 0.0
    ml = cal.predict_proba(vec.transform([clean_text(text)]))[0, 1]
    kw = keyword_toxicity(text)
    return float(1.0 - (1.0 - ml) * (1.0 - kw))

def vosk_transcribe(model, wav_path):
    rec = KaldiRecognizer(model, 16000)
    with wave.open(wav_path, 'rb') as wf:
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)
    return json.loads(rec.FinalResult()).get('text', '')

print('loading engines...', flush=True)
vosk_en = VoskModel(os.path.join(ROOT, 'android', 'ChildApp', 'app', 'src', 'main',
                                 'assets', 'vosk_model_unpacked')) if False else None
# the deployed en-in model isn't unpacked locally; fetch the same small en-in model
EN_DIR = os.path.join(SCRATCH, 'vosk-model-small-en-in-0.4')
if not os.path.isdir(EN_DIR):
    import urllib.request, zipfile
    z = os.path.join(SCRATCH, 'vosk-en-in.zip')
    urllib.request.urlretrieve('https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip', z)
    zipfile.ZipFile(z).extractall(SCRATCH)
vosk_en = VoskModel(EN_DIR)
vosk_hi = VoskModel(os.path.join(SCRATCH, 'vosk-model-small-hi-0.22'))
whisper = WhisperModel('tiny', device='cpu', compute_type='int8')

results = []
for i, (phrase, expected) in enumerate(PHRASES):
    mp3 = os.path.join(SCRATCH, f'mix_{i}.mp3')
    wav = os.path.join(SCRATCH, f'mix_{i}.wav')
    gTTS(phrase, lang='hi').save(mp3)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'quiet', '-i', mp3,
                    '-ar', '16000', '-ac', '1', '-f', 'wav', wav], check=True)
    t_en = vosk_transcribe(vosk_en, wav)
    t_hi = vosk_transcribe(vosk_hi, wav)
    t0 = time.time()
    segs, _info = whisper.transcribe(wav, language=None, beam_size=1)
    t_wh = ' '.join(s.text.strip() for s in segs)
    wh_ms = int((time.time() - t0) * 1000)
    row = {'phrase': phrase, 'expected': expected,
           'vosk_en': {'text': t_en, 'score': round(served_score(t_en), 3)},
           'vosk_hi': {'text': t_hi, 'score': round(served_score(t_hi), 3)},
           'whisper_tiny': {'text': t_wh, 'score': round(served_score(t_wh), 3),
                            'ms': wh_ms}}
    results.append(row)
    print(f"[{expected:7s}] {phrase}", flush=True)
    print(f"   EN : '{t_en}' -> {row['vosk_en']['score']}", flush=True)
    print(f"   HI : '{t_hi}' -> {row['vosk_hi']['score']}", flush=True)
    print(f"   WHI: '{t_wh}' -> {row['whisper_tiny']['score']} ({wh_ms}ms)", flush=True)
    os.remove(mp3); os.remove(wav)

with open(os.path.join(SCRATCH, 'stt_shootout.json'), 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print('[OK] wrote stt_shootout.json')
