"""Fetch and prepare the HASOC 2019 Hindi corpus (Mandl et al., FIRE 2019).

The official distribution is registration-gated (hasocfire.github.io), so this
repo does not redistribute the rows. This script rebuilds the exact files the
pipeline uses from a public research mirror, deterministically:

  data/chat_extra/hasoc2019_hindi.csv     80% train split -> auto-ingested by
                                          retrain_models.assemble_chat_dataset
  data/hasoc2019_hindi_heldout.csv        20% held-out split -> scored by
                                          ml/eval_chat_hindi.py (never trained on)

Split is stratified on the label with seed 42, so every rebuild reproduces the
same rows on both sides. Labels: task_1 HOF (hate/offensive) -> toxic=1, NOT -> 0.

The train CSV carries each row TWICE: the original Devanagari text plus a
colloquial romanisation (ITRANS-based, anusvara->n, lowercased) approximating how
Hinglish is actually typed on a QWERTY keyboard — adopted 2026-08-04 after a
measured trial (romanized held-out PR-AUC 0.61 -> 0.87; CONDA and Devanagari
held within CI at matched precision; >=0.95 precision on all three registers at
the deployed 0.95 threshold). The held-out file stays Devanagari-only;
ml/eval_chat_hindi.py romanises it at evaluation time for the romanized view.
"""
import os
import re
import urllib.request

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = ('https://raw.githubusercontent.com/TharinduDR/HASOC-2019/'
          'master/data/hindi_dataset.tsv')

DEV_RE = re.compile(r'[ऀ-ॿ]')


def romanize(text: str) -> str:
    """Colloquial romanisation of Devanagari (ITRANS base: ch/chh consonants,
    anusvara -> n, diacritic markers stripped, lowercased) — approximates typed
    Hinglish. Non-Devanagari text passes through unchanged."""
    if not DEV_RE.search(text):
        return text
    from indic_transliteration import sanscript
    r = sanscript.transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
    r = r.replace('M', 'n').replace('.n', 'n').replace('~N', 'n').replace('N', 'n')
    return re.sub(r'[.~^]', '', r).lower()


def main():
    dest = os.path.join(ROOT, 'data', 'hasoc_hindi_raw.tsv')
    if not os.path.exists(dest):
        print(f"downloading {MIRROR}")
        urllib.request.urlretrieve(MIRROR, dest)
    df = pd.read_csv(dest, sep='\t')
    out = pd.DataFrame({'text': df['text'].astype(str),
                        'toxic': (df['task_1'].astype(str).str.strip() == 'HOF').astype(int)})
    fit, te = train_test_split(out, test_size=0.2, random_state=42,
                               stratify=out['toxic'])
    rom = pd.DataFrame({'text': fit['text'].map(romanize), 'toxic': fit['toxic']})
    fit_both = pd.concat([fit, rom], ignore_index=True)
    os.makedirs(os.path.join(ROOT, 'data', 'chat_extra'), exist_ok=True)
    fit_both.to_csv(os.path.join(ROOT, 'data', 'chat_extra', 'hasoc2019_hindi.csv'), index=False)
    te.to_csv(os.path.join(ROOT, 'data', 'hasoc2019_hindi_heldout.csv'), index=False)
    print(f"[OK] train80 x2 scripts: {len(fit_both)} rows (toxic {fit_both['toxic'].mean():.3f}) -> data/chat_extra/hasoc2019_hindi.csv")
    print(f"[OK] heldout20 (Devanagari): {len(te)} rows -> data/hasoc2019_hindi_heldout.csv")


if __name__ == '__main__':
    main()
