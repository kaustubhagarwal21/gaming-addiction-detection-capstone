# -*- coding: utf-8 -*-
"""Review 3 deck, Results and Discussion: behaviour and voice ablations on one chart.

Shown on slide 522 ("Ablation across all three models"); the chat ablation keeps its
own chart on the slide before it (results_ablation.png, from review3_results.py).

Every plotted value is read from docs/ablation_results.json (ml/ablation_studies.py,
ablate_behavior / ablate_voice), never typed here. Printed labels come from
tools/project_numbers.NUM where a key exists; the "- augmentation" voice row has no
key, so its label is formatted from the same JSON value.

Size, type, helpers and colours are review3_results.py's (imported, not copied):
8 x 5 in (16:10), 200 dpi, white; 15-18 pt text, so >= 14 pt on a 7.4 in slide chart.
  rust #B95427  the deployed recipe of each model
  grey #888888  the same model retrained with one part changed
PES orange #E07B1A is left out for the reason given there: beside rust it fails the
dataviz skill's normal-vision floor (dE 12.3 < 15); rust vs grey passes (dE 15.5,
deutan 11.6). Identity is never colour alone: the rust rows are labelled "Deployed".

Run:  python tools/figs/review3_ablation_all.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review3_results as R  # noqa: E402  (style, helpers, loaded JSON, NUM)

N, BEH, MINUS = R.N, R.BEH, R.MINUS
VOICE = {r['config']: r for r in R.AB['voice']}


def _group(header, deployed, variants):
    """Header, the deployed bar, then the variants from highest to lowest."""
    return [('h', header), deployed] + sorted(variants, key=lambda r: -r[2])


def _grouped_hbar(title, rows, xmax, name, ax_rect, bar_h=0.58, value_pad=0.012, top_pad=0.6):
    """review3_results._hbar_chart, with a rust reference line per group: it drops from
    the deployed bar's end through that group's variants, so each gap reads directly."""
    fig = R._fig(title)
    ax = fig.add_axes(ax_rect)
    ys, total = R._layout(rows)
    ax.set_xlim(0, xmax)
    ax.set_ylim(total - 0.4, -top_pad)
    R._bare(ax)
    groups = []
    for r, y in zip(rows, ys):
        if r[0] == 'h':
            groups.append([])
            R._head(ax, fig, y, r[1])
            continue
        _, label, val, vlabel, colour = r
        groups[-1].append((y, val))
        R._row_label(ax, y, label)
        R.hbar(ax, y, val, bar_h, colour)
        # a white box under the value keeps the reference line from striking through it
        ax.text(val + value_pad * xmax, y, vlabel, ha='left', va='center',
                fontsize=R.FS_TEXT, color=R.INK, zorder=7,
                bbox=dict(boxstyle='square,pad=0.12', facecolor='white', edgecolor='none'))
    for g in groups:
        R._baseline(ax, g[0][0], g[-1][0])
        (y_dep, x_dep), y_last = g[0], g[-1][0]
        ax.plot([x_dep, x_dep], [y_dep + bar_h / 2, y_last + 0.5], color=R.RUST, lw=1.6,
                zorder=6, solid_capstyle='butt')
    return R._save(fig, name)


def fig_ablation_all():
    beh = _group(
        'Behaviour · accuracy on held-out simulated labels',
        ('b', 'Deployed: 10 features', BEH['objective-10 (deployed)']['accuracy'],
         N['beh_acc'], R.RUST),
        [('b', '+ 10 derived proxies', BEH['all-20 (incl. derived proxies)']['accuracy'],
          N['beh_all20'], R.GREY),
         ('b', 'Pattern features only', BEH['pattern features only (5)']['accuracy'],
          N['beh_pattern_only'], R.GREY),
         ('b', 'Volume features only', BEH['volume features only (5)']['accuracy'],
          N['beh_volume_only'], R.GREY),
         ('b', 'Screen-time hours only',
          BEH['screen-time only (hours, the baseline)']['accuracy'], N['beh_screen_only'],
          R.GREY)])
    aug = VOICE['- augmentation']['accuracy']
    voice = _group(
        'Voice · accuracy on unseen speakers (chance 0.25)',
        ('b', 'Deployed: 36 features', VOICE['full (36 feats, 4 corpora, aug x1)']['accuracy'],
         N['voice_acc_abl'], R.RUST),
        [('b', f'{MINUS} noise augmentation', aug, f'{aug:.3f}', R.GREY),
         ('b', 'English corpora only', VOICE['English-only training corpora']['accuracy'],
          N['voice_english_only'], R.GREY),
         ('b', 'Earlier 17 features', VOICE['17-feature prefix']['accuracy'],
          N['voice_17feat'], R.GREY)])
    return _grouped_hbar('Features carry the accuracy; extras barely move it', beh + voice,
                         1.13, 'ablation_all.png', [0.345, 0.03, 0.64, 0.86])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    fig_ablation_all()
