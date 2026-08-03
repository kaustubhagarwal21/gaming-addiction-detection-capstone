# -*- coding: utf-8 -*-
"""Code-mixed gaming rows in Devanagari, BOTH labels — register made label-neutral.

Measured problem (2026-08-04): ordinary friendly gaming chat, once written in
Devanagari (typed on a Hindi keyboard, or transcribed by a Hindi recogniser),
scored 0.86-0.93 — above the streak bar, near the alert cutoff. Adding clean Hindi
Wikipedia fixed sentences made of NATIVE Hindi words but not those dominated by
English loanwords in Devanagari (गुड गेम, इंटरनेट स्लो): encyclopedic text simply
does not contain that register.

Method: take REAL clean utterances from the CONDA gaming corpus (English, in-domain,
label=clean) and rewrite their common words into the Devanagari forms a Hindi
recogniser/typist actually produces, using a curated loanword map. The map's entries
are grounded — the gaming terms were read off real vosk-model-small-hi-0.22 output
(गुड गेम, लेवल, हार्ड, इंटरनेट, स्लो, टीम, ब्रो, अनइंस्टॉल), the rest are standard
Devanagari spellings of the same words. Rows a map cannot substantially convert are
dropped, so every emitted row is genuinely code-mixed.

Output: data/chat_extra/hindi_gaming_codemixed.csv (CONDA labels kept), both
scripts. Converting only clean rows over-taught "code-mixed gaming = clean" (a
measured abusive transcript fell from 0.73 to 0.45); converting toxic rows too
makes the register itself carry no label signal.
Usage: python ml/make_hindi_gaming_codemixed.py
"""
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# English -> Devanagari, as a Hindi speaker types / a Hindi ASR transcribes them.
LOANWORDS = {
    'game': 'गेम', 'games': 'गेम्स', 'gaming': 'गेमिंग', 'play': 'प्ले',
    'playing': 'प्लेइंग', 'player': 'प्लेयर', 'team': 'टीम', 'level': 'लेवल',
    'map': 'मैप', 'round': 'राउंड', 'match': 'मैच', 'win': 'विन', 'won': 'वन',
    'lose': 'लूज', 'lost': 'लॉस्ट', 'good': 'गुड', 'nice': 'नाइस', 'great': 'ग्रेट',
    'well': 'वेल', 'played': 'प्लेड', 'hard': 'हार्ड', 'easy': 'ईजी',
    'fast': 'फास्ट', 'slow': 'स्लो', 'internet': 'इंटरनेट', 'net': 'नेट',
    'lag': 'लैग', 'ping': 'पिंग', 'server': 'सर्वर', 'connect': 'कनेक्ट',
    'uninstall': 'अनइंस्टॉल', 'install': 'इंस्टॉल', 'update': 'अपडेट',
    'phone': 'फोन', 'mobile': 'मोबाइल', 'battery': 'बैटरी', 'charge': 'चार्ज',
    'bro': 'ब्रो', 'guys': 'गाइज', 'friend': 'फ्रेंड', 'squad': 'स्क्वाड',
    'chat': 'चैट', 'voice': 'वॉइस', 'mic': 'माइक', 'sound': 'साउंड',
    'score': 'स्कोर', 'point': 'पॉइंट', 'points': 'पॉइंट्स', 'rank': 'रैंक',
    'shot': 'शॉट', 'shoot': 'शूट', 'jump': 'जंप', 'run': 'रन', 'move': 'मूव',
    'back': 'बैक', 'front': 'फ्रंट', 'left': 'लेफ्ट', 'right': 'राइट',
    'start': 'स्टार्ट', 'stop': 'स्टॉप', 'wait': 'वेट', 'ready': 'रेडी',
    'time': 'टाइम', 'school': 'स्कूल', 'homework': 'होमवर्क', 'tomorrow': 'टुमॉरो',
    'ok': 'ओके', 'okay': 'ओके', 'yes': 'यस', 'no': 'नो', 'thanks': 'थैंक्स',
    'sorry': 'सॉरी', 'please': 'प्लीज', 'come': 'कम', 'go': 'गो',
    'best': 'बेस्ट', 'better': 'बेटर', 'super': 'सुपर', 'cool': 'कूल',
    'fun': 'फन', 'happy': 'हैप्पी', 'enjoy': 'एंजॉय', 'party': 'पार्टी',
    'lobby': 'लॉबी', 'skin': 'स्किन', 'weapon': 'वेपन', 'gun': 'गन',
    'health': 'हेल्थ', 'heal': 'हील', 'revive': 'रिवाइव', 'cover': 'कवर',
}
# Conversational Hindi glue so rows read like chat, not word lists.
GLUE = ['यार', 'भाई', 'अरे', 'चलो', 'अच्छा', 'ठीक है', 'फिर', 'बहुत', 'थोड़ा', 'क्या']
MIN_CONVERTED = 2          # a row must gain >=2 Devanagari loanwords to count


def convert(text, rng):
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return None, 0
    out, hits = [], 0
    for w in words:
        d = LOANWORDS.get(w)
        if d:
            out.append(d)
            hits += 1
        else:
            out.append(w)
    if hits < MIN_CONVERTED:
        return None, hits
    # sprinkle conversational Hindi glue deterministically
    if rng.random() < 0.6:
        out.insert(rng.integers(0, len(out) + 1), GLUE[int(rng.integers(0, len(GLUE)))])
    return ' '.join(out), hits


def main():
    import numpy as np
    from fetch_hasoc_hindi import romanize
    rng = np.random.default_rng(42)
    src = os.path.join(ROOT, 'data', 'conda', 'CONDA_train.csv')
    df = pd.read_csv(src)
    labels = df['intentClass'].astype(str).str.strip().str.upper().isin({'E', 'I'}).astype(int)
    rows, seen = [], set()
    for t, y in zip(df['utterance'].astype(str), labels):
        conv, _ = convert(t, rng)
        if conv and conv not in seen:
            seen.add(conv)
            rows.append((conv, int(y)))
    n_tox = sum(y for _, y in rows)
    print(f"converted {len(rows)} code-mixed rows ({n_tox} toxic / {len(rows)-n_tox} clean) from {len(df)} CONDA utterances")
    dev = pd.DataFrame({'text': [t for t, _ in rows], 'toxic': [y for _, y in rows]})
    rom = pd.DataFrame({'text': [romanize(t) for t, _ in rows], 'toxic': dev['toxic']})
    out = pd.concat([dev, rom], ignore_index=True)
    dest = os.path.join(ROOT, 'data', 'chat_extra', 'hindi_gaming_codemixed.csv')
    out.to_csv(dest, index=False)
    print(f"[OK] {len(out)} rows (both scripts) -> {dest}")


if __name__ == '__main__':
    main()
