"""
ASR fairness audit across Indian accents — the paper's §9 audit item, executed.

The spoken-chat path is: mic → on-device Vosk Indian-English STT → the served
toxicity scorer. Both halves can be unfair by accent: the STT's word-error rate
(WER) can differ across India's language families, and — more consequentially for
an ALERTING system — a mis-transcription can CREATE a toxic word that was never
said, so the benign-speech false-alert rate can concentrate on whoever the
acoustic model serves worst. This script measures both, stratified.

Data: Svarah (AI4Bharat) — 9.6 h / 6,656 clips of transcribed Indian-English from
117 speakers across 65 districts / 19 states; every clip carries the speaker's
primary language, state, gender and age group. Reference: Javed et al.,
"Svarah: Evaluating English ASR Systems on Indian Accents" (Interspeech 2023).
The download is HuggingFace-login-gated (auto-approved), so the raw parquet is
NOT committed (same policy as HASOC); to reproduce:

  1. Accept conditions at https://huggingface.co/datasets/ai4bharat/Svarah
  2. HF_TOKEN=<read token>; for i in 0 1 2; do
       curl -sL -H "Authorization: Bearer $HF_TOKEN" \
         -o data/svarah/test-0000$i-of-00003.parquet \
         https://huggingface.co/datasets/ai4bharat/Svarah/resolve/main/data/test-0000$i-of-00003.parquet
     done
  3. python ml/eval_asr_fairness.py --transcribe   (resumable; SHARD/N_SHARDS envs
     let several workers split the clips; each worker writes its own jsonl)
  4. python ml/eval_asr_fairness.py --report       → docs/asr_fairness.json

Model: the exact deployed recogniser (vosk-model-small-en-in-0.4), auto-downloaded
from alphacephei.com if VOSK_EN_MODEL doesn't point at an existing copy.

Honesty notes, stated up front:
- Svarah is adult read + conversational speech, not child gaming speech; the audit
  bounds the ACCENT axis, not the domain axis (the domain gap is measured
  separately by the STT shootout's spoken-chat smoke tests).
- Reference transcripts contain digits/formatting that spoken-form hypotheses
  can't match ("11th" vs "eleventh"); normalisation lowercases and strips
  punctuation but does not verbalise numbers, which inflates absolute WER
  slightly and equally across groups — the COMPARISON is the result, not the
  absolute number.
- Groups are reported only at n >= MIN_GROUP_CLIPS to keep estimates meaningful.
"""
import argparse
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

SVARAH_DIR = os.path.join(ROOT, 'data', 'svarah')
SHARDS = [os.path.join(SVARAH_DIR, f'test-0000{i}-of-00003.parquet') for i in range(3)]
HYP_GLOB = os.path.join(SVARAH_DIR, 'hyp_worker{k}.jsonl')
OUT_JSON = os.path.join(ROOT, 'docs', 'asr_fairness.json')
VOSK_URL = 'https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip'
MIN_GROUP_CLIPS = 150
ALERT_T = float(os.environ.get('CHAT_ALERT_T', '0.95'))

# Language family map for the stratification. Svarah's `primary_language` values are
# self-reported; anything unmapped is reported under 'Other' and printed loudly.
FAMILY = {}
for lang in ('Hindi Urdu Bengali Marathi Gujarati Punjabi Odia Oriya Assamese Konkani '
             'Kashmiri Sindhi Nepali Maithili Dogri Bhojpuri Rajasthani Haryanvi '
             'Chhattisgarhi Magahi Awadhi Marwari Sanskrit').split():
    FAMILY[lang] = 'Indo-Aryan'
for lang in 'Tamil Telugu Kannada Malayalam Tulu Kodava Badaga'.split():
    FAMILY[lang] = 'Dravidian'
for lang in 'Manipuri Meitei Bodo Mizo Nagamese Lepcha Sikkimese Nyishi Ao'.split():
    FAMILY[lang] = 'Tibeto-Burman'
for lang in 'Santali Khasi Mundari Ho'.split():
    FAMILY[lang] = 'Austroasiatic'
FAMILY['English'] = 'English-primary'


def _norm(text: str) -> list:
    """ASR-standard normalisation: NFKC, lowercase, strip punctuation, collapse."""
    t = unicodedata.normalize('NFKC', str(text)).lower()
    t = re.sub(r"[^a-z0-9' ]+", ' ', t)
    return t.split()


def _edits(ref: list, hyp: list) -> int:
    """Word-level Levenshtein distance (substitution/insertion/deletion cost 1)."""
    if not ref:
        return len(hyp)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def _load_rows():
    """All Svarah rows across the three shards, with a stable global index."""
    import pyarrow.parquet as pq
    rows = []
    for path in SHARDS:
        if not os.path.exists(path):
            sys.exit(f'missing {path} — see the download recipe in this file\'s docstring')
        rows.append(pq.read_table(path))
    import pyarrow as pa
    table = pa.concat_tables(rows)
    return table


def _vosk_model_dir():
    path = os.environ.get('VOSK_EN_MODEL', '')
    if path and os.path.isdir(path):
        return path
    dest = os.path.join(ROOT, 'data', 'vosk-model-small-en-in-0.4')
    if not os.path.isdir(dest):
        import urllib.request
        z = dest + '.zip'
        print(f'downloading {VOSK_URL} ...', flush=True)
        urllib.request.urlretrieve(VOSK_URL, z)
        with zipfile.ZipFile(z) as f:
            f.extractall(os.path.join(ROOT, 'data'))
        os.remove(z)
    return dest


def transcribe():
    """Resumable worker: transcribe this worker's share of clips to jsonl."""
    import soundfile as sf
    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)

    shard = int(os.environ.get('SHARD', '0'))
    n_shards = int(os.environ.get('N_SHARDS', '1'))
    budget_s = float(os.environ.get('TIME_BUDGET_S', '0')) or None
    out_path = HYP_GLOB.format(k=shard)

    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding='utf-8') as f:
            for line in f:
                try:
                    done.add(json.loads(line)['i'])
                except Exception:
                    pass

    table = _load_rows()
    audio_col = table.column('audio_filepath')
    n = table.num_rows
    mine = [i for i in range(n) if i % n_shards == shard and i not in done]
    print(f'worker {shard}/{n_shards}: {len(mine)} clips to go ({len(done)} done)', flush=True)
    if not mine:
        return

    model = Model(_vosk_model_dir())
    t0 = time.time()
    with open(out_path, 'a', encoding='utf-8') as out:
        for k, i in enumerate(mine):
            if budget_s and time.time() - t0 > budget_s:
                print(f'CHECKPOINT worker {shard}: {k}/{len(mine)} this run — rerun to continue',
                      flush=True)
                sys.exit(3)
            a = audio_col[i].as_py()
            data, sr = sf.read(io.BytesIO(a['bytes']))
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != 16000:
                from scipy.signal import resample_poly
                g = np.gcd(sr, 16000)
                data = resample_poly(data, 16000 // g, sr // g)
            pcm = np.clip(data * 32767.0, -32768, 32767).astype('<i2').tobytes()
            rec = KaldiRecognizer(model, 16000)
            for off in range(0, len(pcm), 64000):
                rec.AcceptWaveform(pcm[off:off + 64000])
            hyp = json.loads(rec.FinalResult()).get('text', '')
            out.write(json.dumps({'i': i, 'hyp': hyp}) + '\n')
            if (k + 1) % 100 == 0:
                out.flush()
                rate = (k + 1) / (time.time() - t0)
                print(f'worker {shard}: {k+1}/{len(mine)}  ({rate:.1f} clips/s)', flush=True)
    print(f'worker {shard}: DONE', flush=True)


def report():
    """Merge worker transcripts; WER + benign-speech alert-FPR by group."""
    import pickle

    import pandas as pd
    from text_utils import clean_text, keyword_toxicity

    table = _load_rows()
    df = table.select([c for c in table.column_names if c != 'audio_filepath']).to_pandas()
    n = len(df)
    hyps = {}
    for k in range(64):
        p = HYP_GLOB.format(k=k)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        hyps[r['i']] = r['hyp']
                    except Exception:
                        pass
    missing = n - len(hyps)
    if missing:
        sys.exit(f'{missing}/{n} clips still untranscribed — run --transcribe to completion first')

    df['hyp'] = [hyps[i] for i in range(n)]
    df['family'] = [FAMILY.get(l, 'Other') for l in df['primary_language']]
    unmapped = sorted(set(df.loc[df['family'] == 'Other', 'primary_language']))
    if unmapped:
        print(f'NOTE: unmapped primary languages -> Other: {unmapped}')

    # ---- WER ----------------------------------------------------------------
    refs = [_norm(t) for t in df['text']]
    hyp_n = [_norm(t) for t in df['hyp']]
    df['edits'] = [_edits(r, h) for r, h in zip(refs, hyp_n)]
    df['ref_words'] = [len(r) for r in refs]

    # ---- served toxicity on the hypothesis (what the system would score) ----
    models_dir = os.path.join(ROOT, 'backend', 'models')
    with open(os.path.join(models_dir, 'tfidf_vectorizer.pkl'), 'rb') as f:
        vec = pickle.load(f)
    cal = os.path.join(models_dir, 'chat_calibrated.pkl')
    with open(cal if os.path.exists(cal) else os.path.join(models_dir, 'chat_model.pkl'), 'rb') as f:
        served = pickle.load(f)

    def alert_rate(texts):
        ml = served.predict_proba(vec.transform([clean_text(t) for t in texts]))[:, 1]
        kw = np.array([keyword_toxicity(t) for t in texts])
        s = 1.0 - (1.0 - ml) * (1.0 - kw)      # noisy-OR, exactly as app.py serves
        return s >= ALERT_T

    df['alert_hyp'] = alert_rate(df['hyp'].tolist())
    df['alert_ref'] = alert_rate(df['text'].tolist())   # control: does the truth alert?

    def group_stats(frame):
        return {
            'clips': int(len(frame)),
            'speech_hours': round(float(frame['duration'].sum()) / 3600, 2),
            'wer': round(float(frame['edits'].sum()) / max(1, int(frame['ref_words'].sum())), 4),
            'alert_fpr_hyp': round(float(frame['alert_hyp'].mean()), 5),
            'alert_fpr_ref': round(float(frame['alert_ref'].mean()), 5),
            'alerts_hyp': int(frame['alert_hyp'].sum()),
        }

    out = {
        'dataset': 'Svarah (AI4Bharat), 6,656 clips / 9.6 h / 117 speakers, HF-gated download',
        'asr_model': 'vosk-model-small-en-in-0.4 (the deployed on-device recogniser)',
        'alert_threshold': ALERT_T,
        'scoring': 'hypothesis -> clean_text -> TF-IDF -> LogReg(+isotonic) noisy-OR keyword '
                   'lexicon, identical to serving; alert_fpr_ref is the same on the human '
                   'reference transcript (the no-ASR control)',
        'overall': group_stats(df),
        'by_language_family': {},
        'by_primary_language': {},
        'by_gender': {},
        'flagged_examples': [],
    }
    for col, key in (('family', 'by_language_family'),
                     ('primary_language', 'by_primary_language'),
                     ('gender', 'by_gender')):
        for g, frame in df.groupby(col):
            if len(frame) >= MIN_GROUP_CLIPS:
                out[key][str(g)] = group_stats(frame)

    for _, r in df[df['alert_hyp']].head(20).iterrows():
        out['flagged_examples'].append({
            'ref': str(r['text'])[:140], 'hyp': str(r['hyp'])[:140],
            'lang': str(r['primary_language']), 'ref_also_alerts': bool(r['alert_ref']),
        })

    print(f"\nOVERALL  wer={out['overall']['wer']:.3f}  "
          f"alert FPR hyp={out['overall']['alert_fpr_hyp']:.4%} "
          f"ref={out['overall']['alert_fpr_ref']:.4%}")
    for key in ('by_language_family', 'by_gender', 'by_primary_language'):
        print(f'\n{key}')
        for g, s in sorted(out[key].items(), key=lambda kv: kv[1]['wer']):
            print(f"  {g:22s} clips={s['clips']:5d}  wer={s['wer']:.3f}  "
                  f"alertFPR={s['alert_fpr_hyp']:.4%}  (ref {s['alert_fpr_ref']:.4%})")

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'\nWrote {OUT_JSON}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--transcribe', action='store_true')
    ap.add_argument('--report', action='store_true')
    args = ap.parse_args()
    if args.transcribe:
        transcribe()
    elif args.report:
        report()
    else:
        ap.error('pass --transcribe or --report')
