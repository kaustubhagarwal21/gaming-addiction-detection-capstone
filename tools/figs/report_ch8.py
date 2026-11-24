# -*- coding: utf-8 -*-
"""Figures for Chapter 8 (Results and Discussion) of the department-format report.

Writes docs/figures/report/ch8_<name>.png: 200 dpi, white background, drawn at the
exact width they are placed at in docs/report/08_results.md (15 cm for full-width
figures, 9.5 cm for the confusion matrices), so every label prints at 9 pt or more.

Every plotted value is read from a committed result file, never retyped:
  docs/ablation_results.json      behaviour / chat / voice ablations (bootstrap CIs)
  docs/figures/chat_scores_cache.npz   per-line chat scores of the ablation run (PR curves)
  docs/survey_extras.json         IGDS9-SF survey: incremental validity, composites
  docs/asr_fairness.json          Svarah accent audit of the speech-to-text path
  docs/fusion_sensitivity.json    replication-gated sensitivity on 131 pilot sessions
  docs/voice_headroom.json        36 acoustic features vs wav2vec2 embeddings
  backend/models/model_metadata.json   confusion matrices, calibration bins
  tools/project_numbers.py        values that live only in the audited report text
                                  (toxic-BERT PR-AUC, device-drill CPU and memory)
The only hand-set constants are the device-drill acceptance gate (TESTING.md: CPU
under 2x the default path, memory under about 400 MB) and the 0.25 chance level of a
four-class problem; both are design rules, not measurements.

Palette (checked with the dataviz validator): PES orange #E07B1A marks the deployed
system or the quantity a figure is about, greys mark baselines and alternatives, rust
#B95427 marks reference lines and paired differences. Orange and rust are never used as
two adjacent fills that the reader must tell apart by colour alone. Orange sits just
under 3:1 contrast on white, so every orange mark carries a printed value label.

Usage:  python tools/figs/report_ch8.py
"""
import json
import os
import re
import sys

import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, 'docs')
OUT = os.path.join(DOCS, 'figures', 'report')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_numbers as pn  # noqa: E402

ORANGE = '#E07B1A'   # deployed system / the quantity the figure is about
RUST = '#B95427'     # reference lines, paired differences
GREY = '#8C8C8C'     # baselines and alternatives (3.4:1 on white)
DARK_GREY = '#5F5F5F'
LIGHT_GREY = '#BDBDBD'
GRID = '#E3E3E3'
AXIS = '#7A7A7A'
INK = '#000000'
CM = 1 / 2.54
DPI = 200

plt.rcParams.update({
    'font.family': ['Arial', 'DejaVu Sans'],
    'font.size': 9,
    'axes.titlesize': 10,
    'axes.titleweight': 'bold',
    'axes.labelsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'text.color': INK,
    'axes.labelcolor': INK,
    'xtick.color': INK,
    'ytick.color': INK,
    'axes.edgecolor': AXIS,
    'axes.linewidth': 0.6,
    'xtick.major.width': 0.6,
    'ytick.major.width': 0.6,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'savefig.facecolor': 'white',
    'axes.unicode_minus': True,
})


# ---------------------------------------------------------------- data loading
def _load(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return json.load(f)


AB = _load('docs/ablation_results.json')
SX = _load('docs/survey_extras.json')
AF = _load('docs/asr_fairness.json')
FS = _load('docs/fusion_sensitivity.json')
VH = _load('docs/voice_headroom.json')
META = _load('backend/models/model_metadata.json')
NUM = pn.NUM

BEH = {r['config']: r for r in AB['behaviour']}
CHAT = {r['config']: r for r in AB['chat']}
VOICE = {r['config']: r for r in AB['voice']}


def _num(key):
    """First number in a project_numbers value ('14%' -> 14.0, '0.709' -> 0.709)."""
    m = re.search(r'-?\d+(?:\.\d+)?', NUM[key].replace(',', ''))
    return float(m.group(0))


def _range(key):
    """'288–301 MB' -> (288.0, 301.0); a single value gives (v, v)."""
    vals = [float(v) for v in re.findall(r'\d+(?:\.\d+)?', NUM[key].replace(',', ''))]
    return (vals[0], vals[-1])


# --------------------------------------------------------------------- helpers
def _figure(width_cm, height_cm, **kw):
    return plt.figure(figsize=(width_cm * CM, height_cm * CM), layout='constrained', **kw)


def _clean(ax, grid_axis='x'):
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.6, linestyle='-')
    ax.set_axisbelow(True)
    ax.tick_params(length=3)


def _overflow(fig):
    """Texts that would be cut off by the figure edge (checked after layout)."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    W, H = fig.bbox.width, fig.bbox.height
    hidden = set()                    # tick labels outside the view limits are not drawn
    for ax in fig.axes:
        for axis, (lo, hi) in ((ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())):
            lo, hi = min(lo, hi), max(lo, hi)
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not lo - 1e-9 <= tick.get_loc() <= hi + 1e-9:
                    hidden.update({id(tick.label1), id(tick.label2)})
    bad = []
    for t in fig.findobj(matplotlib.text.Text):
        if id(t) in hidden or not t.get_visible() or not t.get_text().strip():
            continue
        bb = t.get_window_extent(renderer)
        if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > W + 1 or bb.y1 > H + 1:
            bad.append(' '.join(t.get_text().split()))
    return bad


def _save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f'ch8_{name}.png')
    for text in _overflow(fig):
        print(f'  [WARN] {name}: text runs past the figure edge: {text!r}')
    fig.savefig(path, dpi=DPI, facecolor='white')
    plt.close(fig)
    print('[OK]', os.path.relpath(path, ROOT))


def _pct(x, nd=1):
    return f'{x * 100:.{nd}f}%'


def _minus(text):
    """Typographic minus sign in printed numbers, matching the axis tick labels."""
    return re.sub(r'(?<![\w.])-(?=\d)', '−', text)


def _title(fig, text):
    """Figure-wide title, left-aligned, so a long title is not squeezed into the plot
    area that remains after long category labels."""
    fig.suptitle(text, x=0.01, ha='left', fontsize=10, fontweight='bold')


def _hbars(ax, labels, values, colors, cis=None, fmt='{:.3f}', xmax=1.0, label_pad=0.018):
    """Horizontal bars from a zero baseline, optional CI whiskers, value at the tip."""
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, height=0.58, color=colors, zorder=2)
    for i, v in enumerate(values):
        right = v
        if cis is not None and cis[i] is not None:
            lo, hi = cis[i]
            ax.errorbar(v, y[i], xerr=[[v - lo], [hi - v]], fmt='none', ecolor=INK,
                        elinewidth=0.8, capsize=2.5, capthick=0.8, zorder=3)
            right = hi
        ax.text(right + label_pad * xmax, y[i], fmt.format(v), va='center', ha='left',
                fontsize=9, color=INK)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, xmax)
    _clean(ax, 'x')
    return y


# ----------------------------------------------------------- 1. device drill
def fig_device_drill():
    cpu_def = _num('cpu_default')
    cpu_dual = _range('cpu_dual')
    mem_def = _range('mem_default')          # (mean, peak)
    mem_dual = _range('mem_dual')
    cpu_gate = 2 * cpu_def                   # TESTING.md gate: under 2x the default path
    mem_gate = 400                           # TESTING.md gate: about 400 MB on a 4 GB phone

    fig = _figure(15, 7.2)
    axes = fig.subplots(1, 2)
    cats = ['English STT\n(default)', 'Hindi + English\nSTT (toggle)']
    x = np.arange(2)

    ax = axes[0]
    ax.bar(x, [cpu_def, cpu_dual[0]], width=0.5, color=[ORANGE, GREY], zorder=2)
    ax.errorbar(x[1], cpu_dual[0], yerr=[[0], [cpu_dual[1] - cpu_dual[0]]], fmt='none',
                ecolor=INK, elinewidth=0.8, capsize=3, zorder=3)
    ax.axhline(cpu_gate, color=RUST, lw=1.2, ls='--', zorder=1)
    ax.text(-0.55, cpu_gate + 2.0, f'gate: under 2 × default ({cpu_gate:.0f}%)',
            color=INK, fontsize=9, ha='left', va='bottom')
    ax.text(x[0], cpu_def + 2, NUM['cpu_default'], ha='center', va='bottom')
    ax.text(x[1], cpu_dual[1] + 2, NUM['cpu_dual'], ha='center', va='bottom')
    ax.set_xticks(x, cats)
    ax.set_xlim(-0.6, 1.45)
    ax.set_ylim(0, 90)
    ax.set_ylabel('CPU, % of one core')
    ax.set_title('CPU load', loc='left')
    _clean(ax, 'y')

    ax = axes[1]
    ax.bar(x, [mem_def[0], mem_dual[0]], width=0.5, color=[ORANGE, GREY], zorder=2)
    ax.scatter(x, [mem_def[1], mem_dual[1]], marker='_', s=260, color=INK, lw=1.4, zorder=3)
    ax.axhline(mem_gate, color=RUST, lw=1.2, ls='--', zorder=1)
    ax.text(-0.55, mem_gate + 8, f'gate: about {mem_gate} MB', color=INK, fontsize=9,
            ha='left', va='bottom')
    ax.text(x[0], mem_def[1] + 8, f'{mem_def[0]:.0f} mean\n{mem_def[1]:.0f} peak',
            ha='center', va='bottom')
    ax.text(x[1], mem_dual[1] + 8, f'{mem_dual[0]:.0f} mean\n{mem_dual[1]:.0f} peak',
            ha='center', va='bottom')
    ax.set_xticks(x, cats)
    ax.set_xlim(-0.6, 1.45)
    ax.set_ylim(0, 540)
    ax.set_ylabel('App memory (PSS), MB')
    ax.set_title('Memory (bar = mean, tick = peak)', loc='left')
    _clean(ax, 'y')
    _title(fig, 'ChildApp cost on a Galaxy M52 5G: default passes the gate, dual STT fails')
    _save(fig, 'device_drill')


# ------------------------------------------------------- 2. confusion matrices
SEQ = LinearSegmentedColormap.from_list('pes_seq', ['#FFFFFF', '#F6CFA3', ORANGE, '#8A3A12'])


def _confusion(cm, labels, title, name, xlabel, ylabel, width_cm=9.5, height_cm=8.3):
    cm = np.asarray(cm, dtype=float)
    share = cm / cm.sum(axis=1, keepdims=True)
    fig = _figure(width_cm, height_cm)
    ax = fig.subplots()
    im = ax.imshow(share, cmap=SEQ, vmin=0, vmax=1)
    n = len(labels)
    ax.set_xticks(range(n), labels, rotation=25, ha='right')
    ax.set_yticks(range(n), labels)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc='left')
    for i in range(n):
        for j in range(n):
            dark = share[i, j] > 0.8          # white only on the dark end of the ramp
            ax.text(j, i, f'{int(cm[i, j]):,}\n{share[i, j]:.0%}', ha='center', va='center',
                    fontsize=9, color='white' if dark else INK)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    cb = fig.colorbar(im, ax=ax, shrink=0.9)
    cb.set_label('share of the true class', fontsize=9)
    cb.outline.set_visible(False)
    _save(fig, name)


def fig_confusions():
    names = {'casual': 'Low', 'at_risk': 'Some', 'addicted': 'High'}
    labels = [names[c] for c in META['confusion_labels']]
    _confusion(META['confusion_matrix'], labels,
               'Behaviour model, held-out synthetic split', 'cm_behaviour',
               'Predicted concern class', 'True class (synthetic label)')
    v = META['voice_metrics']
    _confusion(v['confusion'], [c.capitalize() for c in v['confusion_labels']],
               'Voice model, unseen speakers', 'cm_voice',
               'Predicted emotion', 'True emotion (acted corpora)')


# ------------------------------------------------------------- 3. reliability
def fig_reliability():
    cal = META['calibration_eval']
    fig = _figure(15, 7.4)
    axes = fig.subplots(1, 2)
    for ax, key, title in ((axes[0], 'behaviour', 'Behaviour model (3 classes)'),
                           (axes[1], 'chat', 'Chat model (toxic or clean)')):
        ax.plot([0, 1], [0, 1], color=LIGHT_GREY, lw=1, zorder=1)
        for state, color, marker in (('uncalibrated', GREY, 's'), ('calibrated', ORANGE, 'o')):
            bins = cal[key][state]['bins']
            xs = [b['confidence'] for b in bins]
            ys = [b['accuracy'] for b in bins]
            ax.plot(xs, ys, color=color, lw=2, marker=marker, ms=5, zorder=3,
                    label=f'{state} (ECE {cal[key][state]["ece"]:.3f})')
            for b in bins:
                if b['n'] < 20:   # a near-empty bin: say so, do not let it look like a trend
                    ax.annotate(f'n = {b["n"]}', (b['confidence'], b['accuracy']),
                                xytext=(-6, 4), textcoords='offset points', fontsize=9,
                                ha='right')
        ax.set_xlim(0.4, 1.0)
        ax.set_ylim(0.0, 1.02)
        ax.set_xlabel('Stated confidence of the top class')
        ax.set_ylabel('Observed accuracy')
        ax.set_title(title, loc='left')
        ax.legend(loc='lower right', frameon=False)
        _clean(ax, 'both')
    _title(fig, 'Calibration: after isotonic calibration, stated confidence tracks '
                'observed accuracy')
    _save(fig, 'reliability')


# -------------------------------------------------------------- 4. comparison
def _vbars(ax, labels, values, colors, cis=None, fmt='{:.3f}', ylim=(0, 1), pad=0.02):
    x = np.arange(len(labels))
    ax.bar(x, values, width=0.55, color=colors, zorder=2)
    span = ylim[1] - ylim[0]
    for i, v in enumerate(values):
        top = max(v, 0)
        if cis is not None and cis[i] is not None:
            lo, hi = cis[i]
            ax.errorbar(x[i], v, yerr=[[v - lo], [hi - v]], fmt='none', ecolor=INK,
                        elinewidth=0.8, capsize=3, zorder=3)
            top = hi
        ax.text(x[i], top + pad * span, fmt.format(v), ha='center', va='bottom', fontsize=9)
    ax.set_xticks(x, labels)
    ax.set_ylim(*ylim)
    _clean(ax, 'y')


def fig_comparison():
    fig = _figure(15, 13)
    axes = fig.subplots(2, 2)

    scr = BEH['screen-time only (hours, the baseline)']
    dep = BEH['objective-10 (deployed)']
    ax = axes[0, 0]
    _vbars(ax, ['Screen time\nonly', 'Ten behaviour\nfeatures (deployed)'],
           [scr['accuracy'], dep['accuracy']], [GREY, ORANGE],
           [scr['acc_ci95'], dep['acc_ci95']], fmt='{:.1%}')
    ax.set_ylabel('Accuracy')
    ax.set_title('(a) Behaviour, synthetic labels', loc='left')

    inc = SX['incremental']
    ax = axes[0, 1]
    _vbars(ax, ['Self-reported\nhours', 'Behaviour\nscore (deployed)'],
           [inc['rho_hours'], inc['rho_model']], [GREY, ORANGE],
           [inc['rho_hours_ci'], inc['rho_model_ci']], fmt='{:.3f}', ylim=(-0.1, 0.6))
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel('Spearman ρ with IGDS9-SF')
    ax.set_title(f'(b) Behaviour, real survey (n = {inc["n"]})', loc='left')

    orig = CHAT['original (general-only, word-only)']
    full = CHAT['full recipe (deployed)']
    ax = axes[1, 0]
    _vbars(ax, ['Original\nrecipe', 'toxic-BERT\n(off the shelf)', 'Deployed\npipeline'],
           [orig['pr_auc'], _num('toxic_bert'), full['pr_auc']], [GREY, GREY, ORANGE],
           [orig['pr_auc_ci95'], None, full['pr_auc_ci95']])
    ax.set_ylabel('PR-AUC')
    ax.set_title('(c) Chat, held-out gaming chat', loc='left')

    ax = axes[1, 1]
    _vbars(ax, ['36 acoustic\nfeatures (deployed)', 'wav2vec2\nembeddings'],
           [VH['A_36feat_4class']['acc'], VH['B_emb_4class']['acc']], [ORANGE, GREY],
           fmt='{:.3f}')
    ax.axhline(0.25, color=RUST, lw=1.2, ls='--', zorder=1)
    ax.text(0.5, 0.265, 'chance', ha='center', va='bottom', fontsize=9)
    ax.set_ylabel('Accuracy, 4 emotions')
    ax.set_title('(d) Voice, unseen speakers', loc='left')
    _title(fig, 'Each deployed channel against its most relevant alternative')
    _save(fig, 'comparison')


# ------------------------------------------------------------- 5. ablations
CHAT_ROWS = [
    ('full recipe (deployed)', 'Full recipe (deployed)'),
    ('- keyword fusion', '− keyword-list fusion'),
    ('- calibration', '− calibration'),
    ('- char_wb n-grams', '− character n-grams'),
    ('- Davidson corpus', '− Davidson tweets'),
    ('- HASOC Hindi corpus', '− HASOC Hindi corpus'),
    ('- clean-Hindi wiki counterweight', '− clean-Hindi sentences'),
    ('- CONDA corpus (domain data)', '− CONDA gaming chat'),
    ('original (general-only, word-only)', 'Original recipe'),
]


def fig_ablation_chat():
    rows = [CHAT[k] for k, _ in CHAT_ROWS]
    fig = _figure(15, 8.6)
    ax = fig.subplots()
    colors = [ORANGE] + [GREY] * (len(rows) - 1)
    _hbars(ax, [lab for _, lab in CHAT_ROWS], [r['pr_auc'] for r in rows], colors,
           [r['pr_auc_ci95'] for r in rows], xmax=1.0)
    ax.axvline(rows[0]['pr_auc'], color=RUST, lw=1.0, ls='--', zorder=1)
    ax.set_xlabel('PR-AUC on the CONDA validation split (ablation protocol), 95% CI')
    _title(fig, 'Chat ablation: removing the gaming-chat corpus costs far more than '
                'any other change')
    _save(fig, 'ablation_chat')


BEH_ROWS = [
    ('objective-10 (deployed)', 'Ten objective features (deployed)'),
    ('all-20 (incl. derived proxies)', 'All 20 (adds derived proxies)'),
    ('pattern features only (5)', 'Five pattern features only'),
    ('volume features only (5)', 'Five volume features only'),
    ('screen-time only (hours, the baseline)', 'Screen time only (baseline)'),
]
VOICE_ROWS = [
    ('full (36 feats, 4 corpora, aug x1)', 'Full recipe (deployed)'),
    ('- augmentation', '− noise augmentation'),
    ('English-only training corpora', 'English corpora only'),
    ('17-feature prefix', 'First 17 features only'),
]


def fig_ablation_beh_voice():
    fig = _figure(15, 11)
    axes = fig.subplots(2, 1, height_ratios=[5, 4])
    rows = [BEH[k] for k, _ in BEH_ROWS]
    _hbars(axes[0], [lab for _, lab in BEH_ROWS], [r['accuracy'] for r in rows],
           [ORANGE] + [GREY] * 4, [r['acc_ci95'] for r in rows], fmt='{:.1%}')
    axes[0].set_xlabel('Accuracy on the held-out synthetic split, 95% CI')
    axes[0].set_title('(a) Behaviour feature sets', loc='left')
    rows = [VOICE[k] for k, _ in VOICE_ROWS]
    _hbars(axes[1], [lab for _, lab in VOICE_ROWS], [r['accuracy'] for r in rows],
           [ORANGE] + [GREY] * 3, [r['acc_ci95'] for r in rows], fmt='{:.3f}')
    axes[1].axvline(0.25, color=RUST, lw=1.2, ls='--', zorder=1)
    axes[1].set_ylim(-0.6, len(rows) - 0.2)
    axes[1].text(0.262, len(rows) - 0.45, 'chance (0.25)', fontsize=9, va='center')
    axes[1].set_xlabel('Accuracy on unseen speakers (fixed test set), 95% CI')
    axes[1].set_title('(b) Voice training recipes', loc='left')
    _title(fig, 'Behaviour and voice ablations: screen time alone and 17 features fall short')
    _save(fig, 'ablation_beh_voice')


# ---------------------------------------------------------- 6. survey forest
def fig_survey_forest():
    inc = SX['incremental']
    comp = SX['features']['composites']
    rob = SX['robustness']['excluding straight-line']
    rows = [
        ('Behaviour score (primary)', inc['rho_model'], inc['rho_model_ci'], ORANGE),
        ('Score, hours partialled out', inc['partial_rho'], inc['partial_ci'], ORANGE),
        ('Pattern composite', comp['pattern']['rho'], comp['pattern']['ci'], ORANGE),
        (f'Score, n = {rob["n"]} (no straight-liners)', rob['rho'], rob['ci'], ORANGE),
        ('Self-reported hours', inc['rho_hours'], inc['rho_hours_ci'], GREY),
        ('Volume composite', comp['volume']['rho'], comp['volume']['ci'], GREY),
        ('Toxic-chat frequency', SX['chat_premise']['rho'], SX['chat_premise']['ci'],
         DARK_GREY),
    ]
    diffs = [
        ('Score minus hours', inc['delta_rho'], inc['delta_ci']),
        ('Pattern minus volume', comp['pattern_minus_volume']['diff'],
         comp['pattern_minus_volume']['ci']),
    ]
    fig = _figure(15, 11)
    axes = fig.subplots(2, 1, height_ratios=[len(rows), len(diffs) + 0.8], sharex=True)
    text_x = 0.6
    for ax, data, diff in ((axes[0], rows, False), (axes[1], diffs, True)):
        y = np.arange(len(data))[::-1]
        for yi, item in zip(y, data):
            label, est, ci = item[0], item[1], item[2]
            color = RUST if diff else item[3]
            ax.plot([ci[0], ci[1]], [yi, yi], color=INK, lw=1.0, zorder=2)
            ax.plot(est, yi, marker='D' if diff else 'o', ms=7, color=color,
                    markeredgecolor='white', markeredgewidth=1.2, zorder=3)
            sign = '+' if diff else ''
            ax.text(text_x, yi,
                    _minus(f'{est:{sign}.3f}  [{ci[0]:{sign}.3f}, {ci[1]:{sign}.3f}]'),
                    va='center', ha='left', fontsize=9)
        ax.set_yticks(y, [d[0] for d in data])
        ax.axvline(0, color=INK, lw=0.8, zorder=1)
        ax.set_ylim(-0.7, len(data) - 0.3)
        _clean(ax, 'x')
    axes[0].set_xlim(-0.15, 1.08)
    axes[0].set_xticks([-0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5])
    axes[0].text(text_x, len(rows) - 0.45, 'ρ  [95% CI]', fontsize=9, fontweight='bold',
                 va='center')
    axes[0].set_title('(a) Correlation with the IGDS9-SF total', loc='left')
    axes[1].set_title('(b) Paired differences', loc='left')
    axes[1].set_xlabel('Spearman ρ (dot) and 95% bootstrap interval (line)')
    _title(fig, f'External validation on {inc["n"]} scored survey respondents')
    _save(fig, 'survey_forest')


# ------------------------------------------------------- 7. survey features
FEATURE_NAMES = {
    'rapid_relogin_ratio': 'rapid re-login ratio',
    'avg_break_between_sessions_min': 'average break between sessions (reversed)',
    'late_night_play_ratio': 'late-night play ratio',
    'longest_play_streak_days': 'longest play streak',
    'binge_sessions_per_week': 'binge sessions per week',
    'sessions_per_day': 'sessions per day',
    'weekly_play_time_hours': 'weekly play hours',
    'days_played_per_week': 'days played per week',
    'daily_play_time_hours': 'daily play hours',
    'avg_session_duration_min': 'average session duration',
}
PATTERN = {'rapid_relogin_ratio', 'avg_break_between_sessions_min', 'late_night_play_ratio',
           'longest_play_streak_days', 'binge_sessions_per_week'}


def fig_survey_features():
    pf = SX['features']['per_feature']
    order = sorted(pf, key=lambda k: abs(pf[k]), reverse=True)
    fig = _figure(15, 8.6)
    ax = fig.subplots()
    vals = [abs(pf[k]) for k in order]
    colors = [ORANGE if k in PATTERN else GREY for k in order]
    y = np.arange(len(order))[::-1]
    ax.barh(y, vals, height=0.6, color=colors, zorder=2)
    for yi, k in zip(y, order):
        ax.text(abs(pf[k]) + 0.004, yi, _minus(f'{pf[k]:+.3f}'), va='center', fontsize=9)
    ax.set_yticks(y, [FEATURE_NAMES[k] for k in order])
    ax.set_xlim(0, 0.32)
    ax.set_xlabel(f'|ρ| with the IGDS9-SF total (n = {SX["n"]}); labels keep the sign')
    _title(fig, 'Survey: every pattern feature ranks above every volume feature')
    fig.legend(handles=[Patch(color=ORANGE, label='pattern feature (how a person plays)'),
                        Patch(color=GREY, label='volume feature (how much)')],
               loc='outside lower center', ncol=2, frameon=False)
    _clean(ax, 'x')
    _save(fig, 'survey_features')


# ---------------------------------------------------------------- 8. ASR WER
NORTHEAST = {'Bodo', 'Assamese', 'Nepali'}


def fig_asr_wer():
    fam = AF['by_language_family']
    lang = AF['by_primary_language']
    overall = AF['overall']['wer']
    fig = _figure(15, 9.6)
    axes = fig.subplots(1, 2, width_ratios=[1, 1.45])

    ax = axes[0]
    names = list(fam)
    x = np.arange(len(names))
    ax.bar(x, [fam[n]['wer'] for n in names], width=0.64, zorder=2,
           color=[ORANGE if n == 'Tibeto-Burman' else GREY for n in names])
    for xi, n in zip(x, names):   # black inside the bar top: 7:1 on orange, 6:1 on grey
        ax.text(xi, fam[n]['wer'] - 0.015, _pct(fam[n]['wer']), ha='center', va='top')
    ax.axhline(overall, color=RUST, lw=1.2, ls='--', zorder=1)
    ax.set_xticks(x, [n.replace('-', '-\n') + '\n' + f'{fam[n]["clips"]:,} clips'
                      for n in names])
    ax.set_ylim(0, 0.75)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylabel('Word error rate')
    alerts = sum(v['alerts_hyp'] for v in fam.values())
    ax.set_title('(a) By language family', loc='left')
    ax.text(0.02, 0.98, f'False toxicity alerts:\n{alerts} in every family',
            transform=ax.transAxes, ha='left', va='top', fontsize=9)
    _clean(ax, 'y')

    ax = axes[1]
    order = sorted(lang, key=lambda k: lang[k]['wer'])
    y = np.arange(len(order))
    vals = [lang[k]['wer'] for k in order]
    ax.barh(y, vals, height=0.62, color=[ORANGE if k in NORTHEAST else GREY for k in order],
            zorder=2)
    for yi, k in zip(y, order):
        ax.text(lang[k]['wer'] + 0.008, yi, _pct(lang[k]['wer']), va='center', fontsize=9)
    ax.set_yticks(y, order)
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(0, 0.75)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel('Word error rate')
    ax.set_title('(b) By speaker’s first language', loc='left')
    _clean(ax, 'x')
    fig.legend(handles=[Patch(color=ORANGE, label='Northeast-India languages'),
                        Patch(color=GREY, label='other languages'),
                        Line2D([0], [0], color=RUST, lw=1.2, ls='--',
                               label=f'all clips, {_pct(overall)} (a)')],
               loc='outside lower center', ncol=3, frameon=False)
    _title(fig, f'Speech-to-text errors on {AF["overall"]["clips"]:,} Indian-English clips '
                '(deployed recogniser)')
    _save(fig, 'asr_wer')


# ------------------------------------------------------ 9. fusion sensitivity
def fig_fusion_sensitivity():
    ws, gs, cc, fr = (FS['weight_sweep'], FS['genre_sweep'], FS['channel_contribution'],
                      FS['fusion_rule_counterfactual'])
    v = NUM['score_version']
    rows = [
        ('Weights moved ±0.15, median case', ws['median_band_flip'], GREY),
        ('Weights moved ±0.15, worst case', ws['max_band_flip'], GREY),
        ('Band thresholds moved ±0.05, worst case', max(FS['threshold_sweep'].values()), GREY),
        (f'Genre factor removed (score v{v})', gs['x0.0'], ORANGE),
        ('Genre effect halved', gs['x0.5'], GREY),
        ('Genre effect doubled', gs['x2.0'], GREY),
        ('Voice channel dropped', cc['behaviour_only']['band_flip'], GREY),
        ('Behaviour channel dropped', cc['chat_voice_only']['band_flip'], GREY),
        ('Noisy-OR instead of weighted mean', fr['noisy_or']['band_flip'], GREY),
        ('Maximum instead of weighted mean', fr['max']['band_flip'], GREY),
    ]
    fig = _figure(15, 9.4)
    ax = fig.subplots()
    _hbars(ax, [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows],
           fmt='{:.1%}', xmax=0.6, label_pad=0.012)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel(f'Share of the {FS["n"]} pilot sessions whose concern band changes')
    _title(fig, 'Fusion sensitivity: genre and threshold priors move bands far more '
                'than weights')
    _save(fig, 'fusion_sensitivity')


def fig_pr_chat():
    """PR curves of the ablation run (docs/figures/chat_scores_cache.npz, written by
    ml/ablation_studies.py). Labelled by protocol, not 'deployed': these curves are the
    ablation protocol (PR-AUC {chat_prauc}), never the deployed 0.95 operating point."""
    from sklearn.metrics import average_precision_score, precision_recall_curve
    cache = np.load(os.path.join(DOCS, 'figures', 'chat_scores_cache.npz'))
    y = cache['y']
    fig = _figure(12, 8.5)
    ax = fig.subplots()
    for key, label, color, ls in (
            ('full_recipe_(deployed)', 'Full recipe', ORANGE, '-'),
            ('original_(general-only,_word-only)', 'Original recipe (general corpus, words)',
             GREY, '--')):
        p, r, _ = precision_recall_curve(y, cache[key])
        ap = average_precision_score(y, cache[key])
        ax.plot(r, p, color=color, ls=ls, lw=2, label=f'{label}  (PR-AUC {ap:.3f})')
    base = float(y.mean())
    ax.axhline(base, color=RUST, lw=1, ls=':')
    ax.annotate(f'base rate {base:.2f}', xy=(0.02, base), xytext=(0.02, base + 0.03),
                color=RUST, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel('Recall (toxic lines)')
    ax.set_ylabel('Precision (toxic lines)')
    ax.legend(loc='lower left', frameon=False)
    _clean(ax, 'both')
    _title(fig, 'Chat precision-recall, ablation protocol (CONDA validation split)')
    _save(fig, 'pr_chat')


def main():
    fig_device_drill()
    fig_confusions()
    fig_pr_chat()
    fig_reliability()
    fig_comparison()
    fig_ablation_chat()
    fig_ablation_beh_voice()
    fig_survey_forest()
    fig_survey_features()
    fig_asr_wer()
    fig_fusion_sensitivity()


if __name__ == '__main__':
    main()
