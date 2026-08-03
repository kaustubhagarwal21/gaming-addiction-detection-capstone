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
"""
import os
import urllib.request

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = ('https://raw.githubusercontent.com/TharinduDR/HASOC-2019/'
          'master/data/hindi_dataset.tsv')


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
    os.makedirs(os.path.join(ROOT, 'data', 'chat_extra'), exist_ok=True)
    fit.to_csv(os.path.join(ROOT, 'data', 'chat_extra', 'hasoc2019_hindi.csv'), index=False)
    te.to_csv(os.path.join(ROOT, 'data', 'hasoc2019_hindi_heldout.csv'), index=False)
    print(f"[OK] train80: {len(fit)} rows (toxic {fit['toxic'].mean():.3f}) -> data/chat_extra/hasoc2019_hindi.csv")
    print(f"[OK] heldout20: {len(te)} rows -> data/hasoc2019_hindi_heldout.csv")


if __name__ == '__main__':
    main()
