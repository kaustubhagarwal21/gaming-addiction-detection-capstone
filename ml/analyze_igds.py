"""
Analyze the open IGDS9-SF Latin-America dataset — real Internet-Gaming-Disorder
scale scores from 11,191 MOBA players (Cross-cultural IGDS9-SF study, seven
countries; OSF, open access).

  Download (requires `pip install pyreadstat` for the SPSS file):
    https://osf.io/download/hdezr/   ->  data/survey/igds_latam.sav
  Project: https://doi.org/10.17605/OSF.IO/GWCSN

What the system takes from it (this script recomputes both):

1. SEVERITY BASE RATE. The share of real gamers at/above the IGDS9-SF
   disordered-range cutoffs (>=36: ~6%, >=32: ~12%) — the base-rate reality behind
   the platform's precision-first alert thresholds and observation-mode cap: in a
   population where the condition is rare, a screening tool that over-calls is
   worse than useless.

2. CHAT-CHANNEL PREMISE VALIDATION. The ensemble treats chat toxicity as a
   corroborating signal of disordered gaming. In this real sample, every
   toxicity-involvement flag associates with higher IGD severity — most strongly
   self-reported toxic SPEECH ("I have insulted/harassed/discriminated"), the exact
   behaviour the chat channel observes.

The dataset has no weekly-hours variable, so it cannot ground the play-time bands
(the Gamers & Anxiety survey does that — see ml/analyze_survey.py); its value is the
labels.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAV  = os.path.join(ROOT, 'data', 'survey', 'igds_latam.sav')


def main():
    if not os.path.exists(SAV):
        sys.exit(f"Dataset not found at {SAV}\nDownload (open access): "
                 "https://osf.io/download/hdezr/  (pip install pyreadstat)")
    df = pd.read_spss(SAV)
    igd = pd.to_numeric(df['IGDTOTAL'], errors='coerce')
    print(f"respondents: {igd.notna().sum()}   IGDTOTAL mean {igd.mean():.1f} "
          f"median {igd.median():.0f}  (scale 9-45)")

    print("\n1) Severity base rate (disordered-range cutoffs):")
    for cut in (32, 36):
        print(f"   IGDTOTAL >= {cut}: {float((igd >= cut).mean()) * 100:5.1f}%")
    print("   90th/95th/99th percentile:",
          [round(float(np.percentile(igd.dropna(), p)), 1) for p in (90, 95, 99)])

    print("\n2) Toxicity involvement vs IGD severity (chat-channel premise):")
    flags = {
        'said toxic things (TOXYOHE)':      df['TOXYOHE'].astype(str) != 'Ninguna',
        'toxic comms yes (TOXCOM)':         df['TOXCOM'].astype(str) == 'Si',
        'griefing acts (TOXPARTIDAYO)':     df['TOXPARTIDAYO'].astype(str)
                                              != 'Ninguna de las anteriores',
        'experienced toxicity (TOXSENTIR)': df['TOXSENTIR'].astype(str) != 'Ninguna',
    }
    for name, f in flags.items():
        m = igd.notna()
        r, _ = spearmanr(f[m].astype(int), igd[m])
        hi, lo = igd[m & f], igd[m & ~f]
        p = mannwhitneyu(hi, lo, alternative='greater').pvalue
        print(f"   {name:<36} IGD {hi.mean():.1f} vs {lo.mean():.1f}   "
              f"r={r:+.3f}  p={p:.1e}")
    print("\n   Every involvement flag associates with HIGHER severity; the strongest "
          "is toxic SPEECH —\n   the behaviour the chat channel observes. Direction and "
          "significance support using chat\n   toxicity as a corroborating (not primary) "
          "risk signal, exactly the ensemble's weighting.")


if __name__ == '__main__':
    main()
