"""
Paper figures (vector PDFs into docs/figures/):

  pr_chat.pdf       PR curves on held-out real gaming chat: deployed pipeline vs the
                    original general-corpus recipe, with the base-rate floor.
  cm_behaviour.pdf  Behaviour confusion matrix (row-normalised shading + counts).
  cm_voice.pdf      Voice confusion matrix (speaker-independent held-out).

Design rules applied (dataviz method): one hue for magnitude (sequential Blues on the
heatmaps — never a rainbow), two series distinguished by hue AND lightness AND line
style (print/CVD-safe), recessive grid, direct labels, no chartjunk.

Run AFTER ml/ablation_studies.py (it caches the per-example chat scores):
  python ml/make_figures.py
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGS = os.path.join(ROOT, 'docs', 'figures')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.metrics import precision_recall_curve, average_precision_score  # noqa: E402

BLUE, ORANGE, INK, MUTED = '#1d4ed8', '#b45309', '#1f2937', '#6b7280'
plt.rcParams.update({'font.size': 9, 'axes.edgecolor': MUTED,
                     'axes.labelcolor': INK, 'xtick.color': INK, 'ytick.color': INK})


def pr_chat():
    cache = np.load(os.path.join(FIGS, 'chat_scores_cache.npz'))
    y = cache['y']
    series = [('full_recipe_(deployed)', 'Deployed pipeline', BLUE, '-'),
              ('original_(general-only,_word-only)', 'Original (general corpus, word-only)',
               ORANGE, '--')]
    fig, ax = plt.subplots(figsize=(4.8, 3.4))
    for key, label, color, ls in series:
        s = cache[key]
        p, r, _ = precision_recall_curve(y, s)
        ap = average_precision_score(y, s)
        ax.plot(r, p, color=color, ls=ls, lw=2, label=f'{label}  (PR-AUC {ap:.3f})')
    base = float(y.mean())
    ax.axhline(base, color=MUTED, lw=1, ls=':')
    ax.annotate(f'base rate {base:.2f}', xy=(0.02, base), xytext=(0.02, base + 0.03),
                color=MUTED, fontsize=8)
    ax.set_xlabel('Recall (toxic)')
    ax.set_ylabel('Precision (toxic)')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.grid(True, color='#e5e7eb', lw=0.6)
    ax.set_axisbelow(True)
    for s_ in ('top', 'right'):
        ax.spines[s_].set_visible(False)
    ax.legend(loc='lower left', frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, 'pr_chat.pdf'))
    plt.close(fig)
    print('[OK] pr_chat.pdf')


def confusion_heatmap(cm, labels, title, fname):
    cm = np.asarray(cm, dtype=float)
    rownorm = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(3.7, 3.2))
    im = ax.imshow(rownorm, cmap='Blues', vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha='right')
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel('Predicted')
    ax.set_ylabel('Actual')
    ax.set_title(title, fontsize=9)
    for i in range(len(labels)):
        for j in range(len(labels)):
            dark = rownorm[i, j] > 0.5
            ax.text(j, i, f'{int(cm[i, j])}\n{rownorm[i, j]:.0%}',
                    ha='center', va='center', fontsize=8,
                    color='white' if dark else INK)
    fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03).set_label('row share', fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, fname))
    plt.close(fig)
    print(f'[OK] {fname}')


def main():
    os.makedirs(FIGS, exist_ok=True)
    meta = json.load(open(os.path.join(ROOT, 'backend', 'models', 'model_metadata.json')))
    pr_chat()
    nice = {'casual': 'Casual', 'at_risk': 'At-Risk', 'addicted': 'Addicted'}
    confusion_heatmap(meta['confusion_matrix'],
                      [nice.get(l, l) for l in meta['confusion_labels']],
                      'Behaviour model — held-out confusion', 'cm_behaviour.pdf')
    v = meta['voice_metrics']
    confusion_heatmap(v['confusion'], [l.capitalize() for l in v['confusion_labels']],
                      'Voice model — speaker-independent confusion', 'cm_voice.pdf')


if __name__ == '__main__':
    main()
