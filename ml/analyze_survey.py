"""
Ground the system's play-time assumptions in REAL survey data.

Dataset: "Gamers & Anxiety" (Sauter & Draschkow, 2017) — the largest open dataset of
gamers' wellbeing: 13,464 respondents, weekly gaming hours + GAD-7 anxiety + SWL life
satisfaction + demographics. CC-BY 4.0.
  OSF:    https://osf.io/q864d/          (project; GamingStudy_data.csv)
  Mirror: https://raw.githubusercontent.com/TryambakTrambo/gaming-anxiety/main/Gaming%20Data.csv
  -> save as data/survey/GamingStudy_data.csv

This script recomputes, from that file, the constants that two parts of the system
bake in (each cites this script):
  1. The parent-dashboard PEER-COMPARISON table (app.py _PEER_HOURS/_PEER_PERCENTILE):
     weekly-hours -> percentile among gamers aged <=24 (closest cohort to the target
     users). The previous table was hand-set and materially wrong (it placed 10h/week
     at the 45th percentile; the real value is the 20th).
  2. The behaviour-data generator's per-class WEEKLY-HOURS bands
     (ml/retrain_models.py): casual / at-risk / heavy play-time levels now follow the
     empirical distribution segments instead of invented means.

It also reports the hours-vs-wellbeing direction check quoted in the paper.

Run from the project root:  python ml/analyze_survey.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV  = os.path.join(ROOT, 'data', 'survey', 'GamingStudy_data.csv')

MAX_WEEKLY = 112     # 16 h/day x 7 — beyond this is junk (the raw file has e.g. 8000)
YOUNG_AGE  = 24      # closest available cohort to the target users (survey is 18+)

# Generator band definitions (percentile ranges of the young cohort's weekly hours).
# casual = the broad low-to-median mass; at-risk = the heavy upper-middle; the top
# band models problematic-level play. These are DESCRIPTIVE segments of real play
# time — the class labels themselves remain synthetic screening priors.
BANDS = {'casual': (5, 50), 'at_risk': (60, 90), 'addicted': (92, 100)}


def main():
    if not os.path.exists(CSV):
        sys.exit(f"Survey CSV not found at {CSV}\nDownload it (CC-BY 4.0):\n"
                 "  https://raw.githubusercontent.com/TryambakTrambo/gaming-anxiety/main/Gaming%20Data.csv")
    df = pd.read_csv(CSV, encoding='latin-1')
    h = df[['Hours', 'Age', 'GAD_T', 'SWL_T']].dropna(subset=['Hours'])
    h = h[(h['Hours'] > 0) & (h['Hours'] <= MAX_WEEKLY)]
    young = h[h['Age'] <= YOUNG_AGE]
    print(f"valid respondents: {len(h)}   aged<={YOUNG_AGE}: {len(young)}")

    print("\n1) Peer-percentile table (weekly hours -> percentile, aged<=%d):" % YOUNG_AGE)
    for p in (5, 10, 20, 30, 40, 55, 70, 80, 85, 90, 95, 99):
        print(f"   {np.percentile(young['Hours'], p):5.1f} h/week  ->  {p}th percentile")

    print("\n2) Generator weekly-hours bands (aged<=%d):" % YOUNG_AGE)
    y = young['Hours']
    for name, (lo, hi) in BANDS.items():
        seg = y[(y >= np.percentile(y, lo)) & (y <= np.percentile(y, hi))]
        print(f"   {name:<9} pct {lo:>2}-{hi:<3}: mean {seg.mean():5.1f}  sd {seg.std():4.1f}  (n={len(seg)})")

    print("\n3) Direction check (all valid respondents):")
    hh = h.dropna(subset=['GAD_T', 'SWL_T'])
    r1, p1 = spearmanr(hh['Hours'], hh['GAD_T'])
    r2, p2 = spearmanr(hh['Hours'], hh['SWL_T'])
    print(f"   weekly hours vs anxiety (GAD-7):        r={r1:+.3f}  p={p1:.1e}")
    print(f"   weekly hours vs life satisfaction (SWL): r={r2:+.3f}  p={p2:.1e}")
    print("   (direction supports treating heavy play as a risk SIGNAL; the small "
          "magnitude is exactly why hours alone are not the model.)")


if __name__ == '__main__':
    main()
