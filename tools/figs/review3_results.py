# -*- coding: utf-8 -*-
"""Review 3 deck, Results and Discussion section: the five chart PNGs.

Every plotted value is read from committed data, never typed here:
  docs/ablation_results.json    behaviour and chat ablations (ml/ablation_studies.py)
  docs/voice_headroom.json      36 hand-made features vs wav2vec2 embeddings, same split
  docs/survey_validation.json   IGDS9-SF construct validity (ml/eval_behavior_survey.py)
  docs/survey_extras.json       composites, partial and paired deltas (ml/eval_survey_extras.py)
  docs/fusion_sensitivity.json  pilot band-flip sweeps (ml/analyze_fusion_sensitivity.py)
  tools/project_numbers.NUM     the printed labels, plus the paper-sourced literals
                                (toxic-BERT PR-AUC; device-drill CPU and memory)
The one non-measured input is the dual speech-to-text acceptance gate, a design
constant written into TESTING.md (device drill) on 7 Aug 2026, before the
18 Aug measurement; it is named below with that source.

Output: docs/figures/review3/results_*.png, 8 x 5 in (16:10), 200 dpi, white.
Text is 15-18 pt at that size, so it stays >= 14 pt when a slide shows a chart
7.4 in wide or more.

Colour (dataviz skill method, validated with its validate_palette.js on white):
  rust #B95427  ours / deployed / interval excludes zero
  grey #888888  baselines, comparators, reference
  red  #d03b3b  only a failed gate (always with a text mark, never colour alone)
PES orange #E07B1A is not used for bars: against rust it fails the skill's
normal-vision floor (dE 12.3 < 15), and rust vs red is worse (dE 6.6), so the
pairs actually used together are rust+grey (dE 15.5) and grey+red (dE 19.3).

Run:  python tools/figs/review3_results.py
"""
import json
import os
import re
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOCS = os.path.join(ROOT, 'docs')
OUT = os.path.join(DOCS, 'figures', 'review3')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_numbers as P  # noqa: E402

N = P.NUM


def _load(name):
    with open(os.path.join(DOCS, name), encoding='utf-8') as f:
        return json.load(f)


AB = _load('ablation_results.json')
VH = _load('voice_headroom.json')
SV = _load('survey_validation.json')
SX = _load('survey_extras.json')
FS = _load('fusion_sensitivity.json')
BEH = {r['config']: r for r in AB['behaviour']}
CHAT = {r['config']: r for r in AB['chat']}

# Dual speech-to-text acceptance gate (TESTING.md, "Device-metrics drill", set 2026-08-07):
# toggle-ON cost < 2x toggle-OFF (CPU time is the battery proxy on USB) and RAM under ~400 MB.
GATE_CPU_TIMES = 2
GATE_RAM_MB = 400

RUST, GREY, RED = '#B95427', '#888888', '#d03b3b'
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#898781'
GRID, AXIS = '#e1e0d9', '#c3c2b7'
MINUS = '−'

W_IN, H_IN, DPI = 8.0, 5.0, 200
FS_TITLE, FS_HEAD, FS_TEXT, FS_SMALL = 18, 15.5, 16, 15

plt.rcParams.update({
    'font.family': ['Arial', 'DejaVu Sans'],
    'font.size': FS_TEXT,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'savefig.facecolor': 'white',
    'text.color': INK,
    'axes.edgecolor': AXIS,
    'xtick.color': INK2,
    'ytick.color': INK2,
})


# ---------------------------------------------------------------- helpers
def _nums(s):
    """All numbers in a NUM string such as '288–301 MB' -> [288.0, 301.0]."""
    return [float(x) for x in re.findall(r'\d+(?:\.\d+)?', s)]


def _fig(title):
    fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI)
    fig.text(0.025, 0.965, title, fontsize=FS_TITLE, fontweight='bold', color=INK,
             ha='left', va='top')
    return fig


def _bare(ax):
    for side in ('top', 'right', 'left', 'bottom'):
        ax.spines[side].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


def _px(ax):
    """Data units per pixel along x and y (limits and axes position must be final)."""
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform([(0, 0), (1, 1)])
    return abs(x1 - x0), abs(y1 - y0)


def _arc(cx, cy, rx, ry, a0, a1, n=10):
    t = np.linspace(a0, a1, n)
    return list(zip(cx + rx * np.cos(t), cy + ry * np.sin(t)))


def hbar(ax, y, x_end, h, color, x0=0.0, round_end=True, alpha=1.0, r_px=9, z=3):
    """Horizontal bar: square at the baseline x0, rounded at the data end."""
    dx, dy = _px(ax)
    w = x_end - x0
    if w <= 0:
        return
    yb, yt = y - h / 2, y + h / 2
    if not round_end:
        pts = [(x0, yb), (x_end, yb), (x_end, yt), (x0, yt)]
    else:
        rx, ry = min(r_px * dx, w), min(r_px * dy, h / 2)
        pts = [(x0, yb), (x_end - rx, yb)]
        pts += _arc(x_end - rx, yb + ry, rx, ry, -np.pi / 2, 0)
        pts += _arc(x_end - rx, yt - ry, rx, ry, 0, np.pi / 2)
        pts += [(x0, yt)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor='none',
                         alpha=alpha, zorder=z))


def vbar(ax, x, y_end, w, color, y0=0.0, round_end=True, alpha=1.0, r_px=9, z=3):
    """Vertical column: square at the baseline y0, rounded at the top."""
    dx, dy = _px(ax)
    h = y_end - y0
    if h <= 0:
        return
    xl, xr = x - w / 2, x + w / 2
    if not round_end:
        pts = [(xl, y0), (xr, y0), (xr, y_end), (xl, y_end)]
    else:
        rx, ry = min(r_px * dx, w / 2), min(r_px * dy, h)
        pts = [(xl, y0), (xr, y0), (xr, y_end - ry)]
        pts += _arc(xr - rx, y_end - ry, rx, ry, 0, np.pi / 2)
        pts += _arc(xl + rx, y_end - ry, rx, ry, np.pi / 2, np.pi)
        pts += [(xl, y_end - ry)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor='none',
                         alpha=alpha, zorder=z))


def _layout(rows, head_gap=0.45):
    """y position for each row, top-down: bars step 1, headers get extra air above."""
    ys, y = [], 0.0
    for i, r in enumerate(rows):
        if r[0] == 'h' and i > 0:
            y += head_gap
        ys.append(y)
        y += 1.0
    return ys, y


def _row_label(ax, y, text, size=FS_TEXT, color=INK):
    ax.text(-0.015, y, text, transform=ax.get_yaxis_transform(), ha='right', va='center',
            fontsize=size, color=color)


def _head(ax, fig, y, text):
    # header starts at the figure's left margin, in axes coordinates
    left_fig = 0.025
    pos = ax.get_position()
    x_axes = (left_fig - pos.x0) / pos.width
    ax.text(x_axes, y, text, transform=ax.get_yaxis_transform(), ha='left', va='center',
            fontsize=FS_HEAD, fontweight='bold', color=INK2)


def _baseline(ax, y_top, y_bot, x=0.0):
    ax.plot([x, x], [y_top - 0.42, y_bot + 0.42], color=AXIS, lw=1.2, zorder=4,
            solid_capstyle='butt')


def _save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI, facecolor='white')
    plt.close(fig)
    print('wrote', os.path.relpath(path, ROOT))
    return path


def _hbar_chart(title, rows, xmax, name, ax_rect, value_pad=0.012, bar_h=0.56,
                ref=None, note=None, top_pad=0.6):
    """rows: ('h', header) or ('b', label, value, value_label, colour)."""
    fig = _fig(title)
    ax = fig.add_axes(ax_rect)
    ys, total = _layout(rows)
    ax.set_xlim(0, xmax)
    ax.set_ylim(total - 0.4, -top_pad)
    _bare(ax)
    group = []
    for r, y in zip(rows, ys):
        if r[0] == 'h':
            if group:
                _baseline(ax, group[0], group[-1])
            group = []
            _head(ax, fig, y, r[1])
            continue
        _, label, val, vlabel, colour = r
        group.append(y)
        _row_label(ax, y, label)
        hbar(ax, y, val, bar_h, colour)
        # a white box under the value keeps a reference line from striking through it
        ax.text(val + value_pad * xmax, y, vlabel, ha='left', va='center',
                fontsize=FS_TEXT, color=INK, zorder=7,
                bbox=dict(boxstyle='square,pad=0.12', facecolor='white', edgecolor='none'))
    if group:
        _baseline(ax, group[0], group[-1])
    if ref is not None:
        x_ref, y_from, y_to = ref
        ax.plot([x_ref, x_ref], [y_from, y_to], color=RUST, lw=1.6, zorder=6,
                solid_capstyle='butt')
    if note:
        fig.text(0.025, 0.03, note, fontsize=FS_SMALL - 1.5, color=INK2, ha='left',
                 va='bottom')
    return _save(fig, name)


# ---------------------------------------------------------------- 1. comparative
def fig_comparative():
    v36 = VH['A_36feat_4class']['acc']
    rows = [
        ('h', 'Behaviour · accuracy on held-out synthetic labels'),
        ('b', 'Deployed: 10 features', BEH['objective-10 (deployed)']['accuracy'],
         N['beh_acc'], RUST),
        ('b', 'Pattern features only', BEH['pattern features only (5)']['accuracy'],
         N['beh_pattern_only'], RUST),
        ('b', 'Volume features only', BEH['volume features only (5)']['accuracy'],
         N['beh_volume_only'], RUST),
        ('b', 'Screen-time hours only',
         BEH['screen-time only (hours, the baseline)']['accuracy'], N['beh_screen_only'], GREY),
        ('h', 'Chat · PR-AUC on held-out real gaming chat'),
        ('b', 'Ours: TF-IDF + LogReg', CHAT['full recipe (deployed)']['pr_auc'],
         N['chat_prauc'], RUST),
        ('b', 'toxic-BERT (110M)', float(N['toxic_bert']), N['toxic_bert'], GREY),
        ('b', 'Our first model', CHAT['original (general-only, word-only)']['pr_auc'],
         N['chat_original'], GREY),
        ('h', 'Voice · accuracy on the same unseen speakers'),
        ('b', 'Ours: 36 audio features', v36, f'{v36:.3f}', RUST),
        ('b', 'wav2vec2 embeddings', VH['B_emb_4class']['acc'], N['voice_emb'], GREY),
    ]
    return _hbar_chart('Our models win on behaviour and chat, not voice', rows, 1.13,
                       'results_comparative.png', [0.345, 0.03, 0.64, 0.86], bar_h=0.58)


# ---------------------------------------------------------------- 2. chat ablation
def fig_ablation():
    full = CHAT['full recipe (deployed)']['pr_auc']
    keyed = {
        '- keyword fusion': N['no_keyword'],
        '- char_wb n-grams': N['no_charwb'],
        '- Davidson corpus': N['no_davidson'],
        '- CONDA corpus (domain data)': N['no_conda'],
    }
    names = {
        '- calibration': f'{MINUS} calibration',
        '- clean-Hindi wiki counterweight': f'{MINUS} clean Hindi Wikipedia',
        '- HASOC Hindi corpus': f'{MINUS} HASOC Hindi abuse',
        '- keyword fusion': f'{MINUS} keyword list',
        '- Davidson corpus': f'{MINUS} slang tweets (Davidson)',
        '- char_wb n-grams': f'{MINUS} character n-grams',
        '- CONDA corpus (domain data)': f'{MINUS} gaming chat (CONDA)',
    }
    removals = sorted((r for r in AB['chat'] if r['config'] in names),
                      key=lambda r: -r['pr_auc'])
    rows = [('h', 'PR-AUC on held-out real gaming chat, one part removed'),
            ('b', 'Full recipe (deployed)', full, N['chat_prauc'], RUST)]
    for r in removals:
        rows.append(('b', names[r['config']], r['pr_auc'],
                     keyed.get(r['config'], f"{r['pr_auc']:.3f}"), GREY))
    ys, _ = _layout(rows)
    ref = (full, ys[1] + 0.29, ys[-1] + 0.5)  # from the full-recipe bar's end downwards
    return _hbar_chart('Real gaming-chat data is the part that matters', rows, 1.0,
                       'results_ablation.png', [0.375, 0.03, 0.60, 0.86], bar_h=0.58,
                       ref=ref)


# ---------------------------------------------------------------- 3. survey validation
def fig_validation():
    cv = SV['construct_validity']
    inc = SX['incremental']
    comp = SX['features']['composites']
    pmv = comp['pattern_minus_volume']
    rows = [
        ('h', f"Rank correlation with the IGDS9-SF score (n = {cv['n']} adults)"),
        ('d', 'Served behaviour score', cv['rho'], cv['ci95'], N['rho']),
        ('d', 'Score, hours held fixed', inc['partial_rho'], inc['partial_ci'], N['partial']),
        ('d', 'Pattern features (5)', comp['pattern']['rho'], comp['pattern']['ci'], N['pattern']),
        ('d', 'Volume features (5)', comp['volume']['rho'], comp['volume']['ci'], N['volume']),
        ('d', 'Screen-time hours alone', inc['rho_hours'], inc['rho_hours_ci'], N['rho_hours']),
        ('h', 'Paired differences, same respondents'),
        ('d', f'Pattern {MINUS} volume', pmv['diff'], pmv['ci'], N['contrast']),
        ('d', f'Score {MINUS} hours', inc['delta_rho'], inc['delta_ci'], N['delta']),
    ]
    fig = _fig('Pattern features carry the signal; hours alone do not')
    ax = fig.add_axes([0.385, 0.215, 0.585, 0.665])
    ys, total = _layout(rows, head_gap=0.35)
    xmin, xmax = -0.15, 0.62
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(total - 0.45, -0.6)
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color(AXIS)
    ticks = [-0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f'{t:.1f}'.replace('-', MINUS) for t in ticks], fontsize=FS_SMALL)
    ax.tick_params(axis='x', length=0, pad=6)
    ax.set_yticks([])
    # gridlines and the zero line run through each group's rows only, never through a header
    groups, cur = [], []
    for r, y in zip(rows, ys):
        if r[0] == 'h':
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(y)
    groups.append(cur)
    for g in groups:
        y_lo, y_hi = min(g) - 0.5, max(g) + 0.5
        for t in ticks:
            if t != 0.0:
                ax.plot([t, t], [y_lo, y_hi], color=GRID, lw=1.0, zorder=1)
        ax.plot([0, 0], [y_lo, y_hi], color=INK2, lw=1.6, zorder=2)
    for r, y in zip(rows, ys):
        if r[0] == 'h':
            _head(ax, fig, y, r[1])
            continue
        _, label, est, ci, vlabel = r
        colour = RUST if ci[0] > 0 else GREY
        _row_label(ax, y, label)
        ax.plot([ci[0], ci[1]], [y, y], color=colour, lw=3.2, solid_capstyle='round', zorder=3)
        ax.plot([est], [y], marker='o', markersize=12, color=colour, markeredgecolor='white',
                markeredgewidth=1.8, zorder=4)
        ax.text(ci[1] + 0.012, y, vlabel.replace('-', MINUS), ha='left', va='center',
                fontsize=FS_TEXT, color=INK, zorder=5)
    handles = [
        Line2D([0], [0], color=RUST, lw=3.2, marker='o', markersize=11,
               markeredgecolor='white', label='95% interval excludes zero'),
        Line2D([0], [0], color=GREY, lw=3.2, marker='o', markersize=11,
               markeredgecolor='white', label='interval includes zero'),
    ]
    fig.legend(handles=handles, loc='lower left', bbox_to_anchor=(0.02, 0.0), ncol=2,
               frameon=False, fontsize=FS_SMALL, handlelength=1.8, columnspacing=1.6)
    return _save(fig, 'results_validation.png')


# ---------------------------------------------------------------- 4. device gate
def fig_device():
    cpu_def = _nums(N['cpu_default'])[0]
    cpu_dual = _nums(N['cpu_dual'])
    mem_def = _nums(N['mem_default'])
    mem_dual = _nums(N['mem_dual'])
    gate_cpu = GATE_CPU_TIMES * cpu_def
    fig = _fig('Dual speech-to-text breaks the phone budget')
    panels = [
        ('CPU, % of one core', [0.085, 0.27, 0.385, 0.54],
         [(cpu_def,), tuple(cpu_dual)], gate_cpu,
         f'gate {gate_cpu:.0f}%', 85, '%'),
        ('Memory, MB', [0.575, 0.27, 0.385, 0.54],
         [tuple(mem_def), tuple(mem_dual)], GATE_RAM_MB,
         f'gate {GATE_RAM_MB} MB', 480, ''),
    ]
    names = ['Default\nEnglish only', 'Dual\nHindi+English']
    x_lo, x_hi = -0.55, 1.55
    for title, rect, vals, gate, gate_lbl, ymax, unit in panels:
        ax = fig.add_axes(rect)
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(0, ymax)
        _bare(ax)
        ax.plot([x_lo, x_hi], [0, 0], color=AXIS, lw=1.2, zorder=4)
        fig.text(rect[0] - 0.06, rect[1] + rect[3] + 0.045, title, fontsize=FS_HEAD,
                 fontweight='bold', color=INK2, ha='left', va='bottom')
        w = 0.56
        for i, v in enumerate(vals):
            colour = GREY if i == 0 else RED
            lo, hi = v[0], v[-1]
            if hi > lo:
                gap = 2 * _px(ax)[1]
                vbar(ax, i, lo, w, colour, round_end=False)
                vbar(ax, i, hi, w, colour, y0=lo + gap, alpha=0.42)
                txt = f'{lo:.0f}–{hi:.0f}{unit}'
            else:
                vbar(ax, i, hi, w, colour)
                txt = f'{hi:.0f}{unit}'
            mark = '✓ within gate' if hi < gate else '✗ over gate'
            ax.text(i, hi + ymax * 0.03, txt, ha='center', va='bottom', fontsize=FS_TEXT,
                    color=INK, zorder=6)
            ax.text(i, -ymax * 0.04, names[i], ha='center', va='top', fontsize=FS_SMALL,
                    color=INK, zorder=6, linespacing=1.15)
            ax.text(i, -ymax * 0.26, mark, ha='center', va='top', fontsize=FS_SMALL,
                    color=INK2, zorder=6)
        ax.plot([x_lo, x_hi], [gate, gate], color=INK2, lw=2.0, ls=(0, (5, 3)), zorder=7)
        ax.text(x_lo + 0.02, gate + ymax * 0.02, gate_lbl, ha='left', va='bottom',
                fontsize=FS_SMALL, color=INK2, zorder=7)
    fig.text(0.025, 0.025, 'Light top: the spread up to the highest reading.',
             fontsize=FS_SMALL - 1.5, color=INK2, ha='left', va='bottom')
    return _save(fig, 'results_device.png')


# ---------------------------------------------------------------- 5. pilot sensitivity
def fig_pilot():
    ws = FS['weight_sweep']
    beh_only_flip = FS['channel_contribution']['behaviour_only']['band_flip']
    rows = [
        ('h', f"Share of {FS['n']} pilot sessions whose concern band changes"),
        ('b', 'Fusion weights ±0.15, median', ws['median_band_flip'],
         N['weight_flip_median'], GREY),
        ('b', 'Fusion weights ±0.15, worst', ws['max_band_flip'], N['weight_flip_max'], GREY),
        ('b', 'Band cut-offs ±0.05, worst', max(FS['threshold_sweep'].values()),
         N['threshold_flip_max'], GREY),
        ('b', f"Behaviour alone ({FS['channel_contribution']['behaviour_only']['usable_rows']} usable)",
         beh_only_flip, f'{beh_only_flip * 100:.1f}%', GREY),
        ('b', 'Genre weight removed', FS['genre_sweep']['x0.0'], N['genre_band_shift'], RUST),
    ]
    return _hbar_chart('Removing the genre weight moved the most bands', rows, 0.43,
                       'results_pilot.png', [0.405, 0.05, 0.545, 0.83], bar_h=0.5,
                       top_pad=0.45)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for f in (fig_comparative, fig_ablation, fig_validation, fig_device, fig_pilot):
        f()
