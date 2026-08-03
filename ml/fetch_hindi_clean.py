# -*- coding: utf-8 -*-
"""Clean natural-Devanagari counterweight for the chat corpus.

Motivation (measured 2026-08-04): the only Devanagari training rows were HASOC
2019 tweets at a 53% offensive base rate, so the model learned a script-level
prior — ordinary friendly Hindi/code-mixed chat transcribed to Devanagari scored
0.78-0.88, above the 0.6 streak bar (false "repeated concerning language" alerts)
and near the per-message cutoff. Fix: add clean, natural Devanagari sentences so
script stops being a toxicity feature.

Source: Hindi Wikipedia (wikimedia/wikipedia 20231101.hi snapshot, CC-BY-SA),
streamed — no full-dump download. Encyclopedic register (stated limitation: not
conversational), but rich in the Devanagari-script English loanwords (गेम, लेवल,
इंटरनेट) that the Vosk Hindi recogniser emits for gaming vocabulary.

Deterministic: fixed snapshot + fixed article order (streaming) + fixed per-article
sentence cap + fixed target count. Emits each sentence in BOTH scripts (original
Devanagari + the same colloquial romanisation used for HASOC) to also drain the
romanized-register prior. Output: data/chat_extra/hindi_clean_wiki.csv (toxic=0).

Usage: pip install datasets; python ml/fetch_hindi_clean.py
"""
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGET_SENTENCES = 8000
PER_ARTICLE_CAP = 6
MIN_LEN, MAX_LEN = 20, 160
DEV_RE = re.compile(r'[ऀ-ॿ]')


def main():
    from datasets import load_dataset
    from fetch_hasoc_hindi import romanize
    ds = load_dataset('wikimedia/wikipedia', '20231101.hi', split='train',
                      streaming=True)
    rows, seen = [], 0
    for art in ds:
        seen += 1
        taken = 0
        for raw in re.split(r'[।\n]', art.get('text', '')):
            s = ' '.join(raw.split())
            if not (MIN_LEN <= len(s) <= MAX_LEN):
                continue
            if not DEV_RE.search(s):
                continue
            if re.search(r'[=\[\]{}|<>]', s):          # markup remnants
                continue
            rows.append(s)
            taken += 1
            if taken >= PER_ARTICLE_CAP or len(rows) >= TARGET_SENTENCES:
                break
        if len(rows) >= TARGET_SENTENCES:
            break
    print(f"collected {len(rows)} clean sentences from {seen} articles")
    dev = pd.DataFrame({'text': rows, 'toxic': 0})
    rom = pd.DataFrame({'text': [romanize(t) for t in rows], 'toxic': 0})
    out = pd.concat([dev, rom], ignore_index=True)
    os.makedirs(os.path.join(ROOT, 'data', 'chat_extra'), exist_ok=True)
    dest = os.path.join(ROOT, 'data', 'chat_extra', 'hindi_clean_wiki.csv')
    out.to_csv(dest, index=False)
    print(f"[OK] {len(out)} rows (both scripts) -> {dest}")


if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
