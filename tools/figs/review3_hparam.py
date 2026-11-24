# -*- coding: utf-8 -*-
"""Hyperparameter sensitivity of the three models: one figure, two sizes.

  docs/figures/review3/hparam_sensitivity.png  8 x 5 in (16:10), 200 dpi: deck slide 525
  docs/figures/report/ch8_hparam.png           15 cm wide, 200 dpi: report Chapter 8

Left panel, one row per model: the spread of the search metric over the whole grid
(CV macro-F1 for behaviour and voice, validation PR-AUC for chat; training data only),
drawn relative to the deployed setting, so the three rows share one scale and every
deployed dot sits at 0. The search-best setting is the right end of each range.
Right panel: the test set, scored once, as the paired difference best - deployed with
its 95% bootstrap interval against a zero line (0 = the deployed setting).

Plotted values come from docs/hparam_behaviour.json, docs/hparam_chat.json and
docs/hparam_voice.json (ml/hparam_*.py); every printed number is a
tools/project_numbers.NUM hp_* key, never typed here. A verdict label is printed only if
the interval agrees with it (gain: CI above 0, loss: CI below 0, tie: CI spans 0).

Colour (dataviz skill validator on white, all pairs):
  slide   rust #B95427 deployed (and the zero line), ink #0b0b0b search-best and its
          test difference, grey #888888 the grid spread (rust-grey dE 15.5, deutan 11.6;
          rust-ink 44.0). Same roles as tools/figs/review3_results.py.
  report  PES orange #E07B1A deployed, rust #B95427 the paired differences, ink the
          search-best ring, grey #8C8C8C the grid spread (orange-grey dE 16.4, protan 13.0),
          as in tools/figs/report_ch8.py. Orange is under 3:1 on white, so every orange dot
          carries a printed label; orange and rust never share a panel.
Identity is never colour alone: filled dot = deployed, open ring = search-best, both
labelled and named in the legend.

Run:  python tools/figs/review3_hparam.py
"""
import json
import os
import re
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOCS = os.path.join(ROOT, 'docs')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_numbers as P  # noqa: E402

N = P.NUM
MINUS = '−'
WHITE_BOX = dict(boxstyle='square,pad=0.14', facecolor='white', edgecolor='none')

SLIDE = dict(
    out=os.path.join(DOCS, 'figures', 'review3', 'hparam_sensitivity.png'),
    W=8.0, H=5.0, dpi=200, pad=0.2, panel_gap=0.5, left_frac=0.54,
    fs_title=18, fs_head=15.5, fs_text=15, fs_name=16,
    dep='#B95427', best='#0b0b0b', diff='#0b0b0b', zero='#B95427', spread='#888888',
    ink='#0b0b0b', ink2='#52514e', axis='#c3c2b7',
    bar_lw=7.0, ms=11.0, edge=2.0, whisk_lw=2.4, zero_lw=1.6, axis_lw=1.2,
    title='A full search: one small gain, one loss, one tie',
    row_gap=0.16, bar_h=0.34)

REPORT = dict(
    out=os.path.join(DOCS, 'figures', 'report', 'ch8_hparam.png'),
    W=15 / 2.54, H=None, dpi=200, pad=0.06, panel_gap=0.3, left_frac=0.54,
    fs_title=10, fs_head=9, fs_text=9, fs_name=9,
    dep='#E07B1A', best='#000000', diff='#B95427', zero='#5F5F5F', spread='#8C8C8C',
    ink='#000000', ink2='#5F5F5F', axis='#7A7A7A',
    bar_lw=4.5, ms=6.5, edge=1.2, whisk_lw=1.5, zero_lw=0.9, axis_lw=0.6,
    title='Tuning on training data: one small gain, one loss, one tie on the test sets',
    row_gap=0.1, bar_h=0.2)

MODELS = (
    # key, JSON, row name, search metric, verdict class + text (checked against the CI)
    ('beh', 'hparam_behaviour.json', 'Behaviour', 'CV macro-F1',
     'gain', 'Small gain, on simulated labels'),
    ('chat', 'hparam_chat.json', 'Chat', 'validation PR-AUC',
     'loss', 'C = {hp_chat_best_c} is worse; C = {hp_chat_deployed_c} stays'),
    ('voice', 'hparam_voice.json', 'Voice', 'CV macro-F1',
     'tie', 'No detectable gain'),
)


def _minus(s):
    return re.sub(r'(?<![\w.])-(?=\d)', MINUS, s)


def _ci_class(lo, hi):
    return 'gain' if lo > 0 else 'loss' if hi < 0 else 'tie'


def rows():
    out = []
    for key, fname, name, metric, verdict_cls, verdict in MODELS:
        with open(os.path.join(DOCS, fname), encoding='utf-8') as f:
            J = json.load(f)
        if not J['replication']['match']:
            raise SystemExit(f'{fname}: replication gate failed; nothing to plot')
        p = 'hp_' + key
        lo, hi = J['test']['diff_ci95']
        if _ci_class(lo, hi) != verdict_cls:
            raise SystemExit(f'{fname}: CI [{lo}, {hi}] no longer reads as {verdict_cls!r}; '
                             'rewrite the verdict labels (and the slide and report text)')
        dep = J['cv_deployed']['mean']
        out.append(dict(
            name=name, head=f"{N[p + '_configs']} settings, {metric}",
            lo_cv=J['cv_spread']['min'] - dep, hi_cv=J['cv_spread']['max'] - dep,
            diff=J['test']['diff'], lo=lo, hi=hi,
            min_lab=N[p + '_cv_min'], best_lab=f"best {N[p + '_cv_max']}",
            dep_lab=f"deployed {N[p + '_cv_deployed']}, rank {N[p + '_rank']} of "
                    f"{N[p + '_configs']}",
            verdict=P.fill(verdict),
            val_lab=_minus(f"{N[p + '_gain']} {N[p + '_gain_ci']}")))
    return out


# ---------------------------------------------------------------- measuring
_MFIG = plt.figure(figsize=(4, 1), dpi=200)
_MREN = _MFIG.canvas.get_renderer()


def tw(s, size, weight='normal'):
    """Rendered width of a text in inches."""
    t = _MFIG.text(0, 0, s, fontsize=size, fontweight=weight, family=['Arial', 'DejaVu Sans'])
    w = t.get_window_extent(_MREN).width / _MFIG.dpi
    t.remove()
    return w


def lh(size):
    return size * 1.28 / 72


def _ticks(lo, hi, steps=(0.01, 0.02, 0.05)):
    for st in steps:
        k0, k1 = int(-(-lo // st)), int(hi // st)     # ceil, floor
        if k1 - k0 + 1 <= 5:
            return [k * st for k in range(k0, k1 + 1)]
    return [0.0]


def _tick_label(v, zero):
    if abs(v) < 1e-12:
        return zero
    return _minus(f'{v:+.2f}')


# ---------------------------------------------------------------- drawing
def render(S, R):
    fs, g = S['fs_text'], S['fs_text'] / 72 * 0.45          # g: label gap
    # vertical layout, top-down, in inches from the top edge
    top = S['pad'] * 0.7
    y_title = top
    y_head = y_title + lh(S['fs_title']) + lh(fs) * 0.5
    y_sub = y_head + lh(S['fs_head'])
    y = y_sub + lh(fs) + lh(fs) * 0.45

    def natural(row_gap):
        h = y + len(R) * (lh(fs) + S['bar_h'] + lh(fs)) + (len(R) - 1) * row_gap
        return h + lh(fs) * 0.35 + 0.06 + lh(fs) + lh(fs) * 0.35 + lh(fs) + S['pad'] * 0.6

    row_gap = S['row_gap']
    if S['H']:
        row_gap += (S['H'] - natural(row_gap)) / (len(R) - 1)
        if row_gap < 0.04:
            raise SystemExit(f"{S['out']}: content does not fit a {S['H']} in figure")
    H = S['H'] or natural(row_gap)
    W = S['W']

    fig = plt.figure(figsize=(W, H), dpi=S['dpi'])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)                     # y grows downwards: positions read top-down
    ax.axis('off')

    def text(x, yy, s, size=fs, color=S['ink'], weight='normal', ha='left', va='top',
             box=False, z=6):
        ax.text(x, yy, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va,
                zorder=z, bbox=WHITE_BOX if box else None,
                family=['Arial', 'DejaVu Sans'])

    xl0 = S['pad']
    inner = W - 2 * S['pad'] - S['panel_gap']
    xl1 = xl0 + inner * S['left_frac']
    xr0, xr1 = xl1 + S['panel_gap'], W - S['pad']

    # ---- left scale: the widest one at which every row's labels fit in the panel
    w_min = [tw(r['min_lab'], fs) for r in R]
    w_best = [tw(r['best_lab'], fs) for r in R]
    w_dep = [tw(r['dep_lab'], fs) for r in R]
    s = 400.0
    while s > 1:
        lo_x = max([xl0 + wm + g - r['lo_cv'] * s for r, wm in zip(R, w_min)] +
                   [xl0 + wd / 2 for wd in w_dep])
        hi_x = min([xl1 - wb - g - r['hi_cv'] * s for r, wb in zip(R, w_best)] +
                   [xl1 - wd / 2 for wd in w_dep])
        if lo_x <= hi_x:
            break
        s *= 0.985
    x_dep = (lo_x + hi_x) / 2

    def xl(d):
        return x_dep + d * s

    # ---- right scale: symmetric about 0, a 0.005 step above the widest interval end
    big = max(max(abs(r['lo']), abs(r['hi'])) for r in R) * 1.15
    rng = (int(big / 0.005) + 2) * 0.005

    def xr(d):
        return xr0 + (d + rng) / (2 * rng) * (xr1 - xr0)

    # ---- title and column heads
    text(xl0, y_title, S['title'], size=S['fs_title'], weight='bold')
    text(xl0, y_head, 'Search on training data only', size=S['fs_head'], weight='bold')
    text(xl0, y_sub, 'whole grid, relative to the deployed setting', color=S['ink2'])
    text(xr0, y_head, 'Test set, scored once', size=S['fs_head'], weight='bold')
    text(xr0, y_sub, f'best {MINUS} deployed, 95% interval', color=S['ink2'])

    # ---- rows
    yy = y
    bar_ys = []
    for r in R:
        # left: model name + grid, range bar, deployed dot, best ring, labels
        text(xl0, yy, r['name'], size=S['fs_name'], weight='bold')
        text(xl0 + tw(r['name'], S['fs_name'], 'bold') + g * 1.4, yy + (lh(S['fs_name']) - lh(fs)) / 2,
             r['head'], color=S['ink2'])
        text(xr0, yy, r['verdict'], weight='bold', box=True)
        yb = yy + lh(fs) + S['bar_h'] / 2
        bar_ys.append(yb)
        cap = S['bar_lw'] / 72 / 2                       # round caps reach past the ends
        ax.plot([xl(r['lo_cv']) + cap, xl(r['hi_cv']) - cap], [yb, yb], color=S['spread'],
                lw=S['bar_lw'], solid_capstyle='round', zorder=2)
        ax.plot([xl(r['hi_cv'])], [yb], marker='o', ms=S['ms'], mfc='white',
                mec=S['best'], mew=S['edge'] * 1.1, zorder=4, ls='none')
        ax.plot([xl(0)], [yb], marker='o', ms=S['ms'], mfc=S['dep'], mec='white',
                mew=S['edge'], zorder=5, ls='none')
        text(xl(r['lo_cv']) - g, yb, r['min_lab'], color=S['ink2'], ha='right', va='center')
        text(xl(r['hi_cv']) + g * 1.3, yb, r['best_lab'], ha='left', va='center')
        y_below = yb + S['bar_h'] / 2
        text(xl(0), y_below, r['dep_lab'], ha='center', box=True)

        # right: paired difference with its interval
        cap_h = S['bar_h'] * 0.42
        ax.plot([xr(r['lo']), xr(r['hi'])], [yb, yb], color=S['diff'], lw=S['whisk_lw'],
                solid_capstyle='butt', zorder=4)
        for e in (r['lo'], r['hi']):
            ax.plot([xr(e), xr(e)], [yb - cap_h / 2, yb + cap_h / 2], color=S['diff'],
                    lw=S['whisk_lw'], solid_capstyle='butt', zorder=4)
        ax.plot([xr(r['diff'])], [yb], marker='o', ms=S['ms'], mfc=S['diff'], mec='white',
                mew=S['edge'], zorder=5, ls='none')
        wv = tw(r['val_lab'], fs)
        cx = min(max(xr(r['diff']), xr0 + wv / 2 + 0.02), xr1 - wv / 2 - 0.02)
        text(cx, y_below, r['val_lab'], ha='center', box=True)
        yy = y_below + lh(fs) + row_gap

    # ---- axes at the bottom: ticks in units of the panel's own metric
    y_ax = yy - row_gap + lh(fs) * 0.35
    tick = 0.06
    vis_lo, vis_hi = (xl0 - x_dep) / s, (xl1 - x_dep) / s
    for (a0, a1, ticks, fx, zero) in (
            (xl0, xl1, _ticks(vis_lo, vis_hi), xl, '0 = deployed'),
            (xr0, xr1, [-0.02, 0.0, 0.02] if rng > 0.02 else [-rng, 0.0, rng], xr,
             '0 = deployed')):
        ax.plot([a0, a1], [y_ax, y_ax], color=S['axis'], lw=S['axis_lw'], zorder=1,
                solid_capstyle='butt')
        for v in ticks:
            ax.plot([fx(v), fx(v)], [y_ax, y_ax + tick], color=S['axis'], lw=S['axis_lw'],
                    zorder=1)
            text(fx(v), y_ax + tick + 0.02, _tick_label(v, zero), color=S['ink2'],
                 ha='center')
    # minor ticks at 0.01 on the test panel
    k = 1
    while k * 0.01 < rng - 1e-9:
        for v in (-k * 0.01, k * 0.01):
            ax.plot([xr(v), xr(v)], [y_ax, y_ax + tick * 0.6], color=S['axis'],
                    lw=S['axis_lw'], zorder=1)
        k += 1
    # zero line of the test panel: the deployed setting
    ax.plot([xr(0), xr(0)], [bar_ys[0] - S['bar_h'] * 0.75, y_ax], color=S['zero'],
            lw=S['zero_lw'], zorder=3, solid_capstyle='butt')

    # ---- legend (identity is never colour alone)
    y_leg = y_ax + tick + 0.02 + lh(fs) + lh(fs) * 0.35
    x = xl0
    yc = y_leg + lh(fs) / 2 - 0.01
    ms = S['ms']
    r_mk = ms / 72 / 2                                   # marker radius, inches
    items = (('dot', 'deployed'), ('ring', 'best'), ('bar', 'whole grid'))
    for kind, lab in items:
        if kind == 'dot':
            ax.plot([x + r_mk], [yc], marker='o', ms=ms, mfc=S['dep'], mec='white',
                    mew=S['edge'], ls='none', zorder=5)
            x += 2 * r_mk + g * 1.2
        elif kind == 'ring':
            ax.plot([x + r_mk], [yc], marker='o', ms=ms, mfc='white', mec=S['best'],
                    mew=S['edge'] * 1.1, ls='none', zorder=5)
            x += 2 * r_mk + g * 1.2
        else:
            ln = fs / 72 * 1.5
            ax.plot([x + S['bar_lw'] / 144, x + ln - S['bar_lw'] / 144], [yc, yc],
                    color=S['spread'], lw=S['bar_lw'], solid_capstyle='round', zorder=2)
            x += ln + g * 1.2
        text(x, yc, lab, color=S['ink2'], va='center')
        x += tw(lab, fs) + fs / 72 * 1.6
    if x - fs / 72 * 1.6 > xl1 + 0.02:
        print(f"  [WARN] {os.path.basename(S['out'])}: legend runs past the left panel")
    # the test panel's unit, under its axis
    text((xr0 + xr1) / 2, yc, 'test accuracy; chat: PR-AUC', color=S['ink2'], ha='center',
         va='center')

    os.makedirs(os.path.dirname(S['out']), exist_ok=True)
    _check_overflow(fig, S['out'])
    fig.savefig(S['out'], dpi=S['dpi'], facecolor='white')
    plt.close(fig)
    print('wrote', os.path.relpath(S['out'], ROOT), f'({W:.2f} x {H:.2f} in)')


def _check_overflow(fig, name):
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
    Wp, Hp = fig.bbox.width, fig.bbox.height
    boxes = []
    for t in fig.findobj(matplotlib.text.Text):
        if not t.get_text().strip() or not t.get_visible():
            continue
        bb = t.get_window_extent(ren)
        if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > Wp + 1 or bb.y1 > Hp + 1:
            print(f'  [WARN] {os.path.basename(name)}: text past the edge: {t.get_text()!r}')
        boxes.append((t.get_text(), bb))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            if a.x0 < b.x1 - 1 and b.x0 < a.x1 - 1 and a.y0 < b.y1 - 1 and b.y0 < a.y1 - 1:
                print(f'  [WARN] {os.path.basename(name)}: labels overlap: '
                      f'{boxes[i][0]!r} / {boxes[j][0]!r}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    R = rows()
    render(SLIDE, R)
    render(REPORT, R)
