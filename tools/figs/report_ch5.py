# -*- coding: utf-8 -*-
"""Figures for Chapter 5 (System Design) of the project report.

Draws seven diagrams with matplotlib patches and saves each as a 200-dpi PNG that is
exactly 15 cm wide, so the report places it at 1:1 scale and every label stays at
9 pt or larger:

  docs/figures/report/ch5_architecture.png   three-tier architecture
  docs/figures/report/ch5_deployment.png     deployment view
  docs/figures/report/ch5_dataflow.png       data flow from capture to the parent
  docs/figures/report/ch5_er.png             entity-relationship view of the schema
  docs/figures/report/ch5_seq_session.png    sequence: game session -> parent alert
  docs/figures/report/ch5_seq_feedback.png   sequence: verdict and nudge round trip
  docs/figures/report/ch5_states.png         session lifecycle + keyboard layout states

Facts are read from the code where that is cheap (the table and column inventory and
the number of API operations come from backend/app.py), and the one plotted number
that lives in a committed JSON (the chat alert threshold) comes from
tools/project_numbers.py, so the diagrams cannot drift silently from the system.
Every figure is checked for text that overflows its box or collides with other text;
problems are printed as WARN lines.

Run from the repository root:  python tools/figs/report_ch5.py
"""
import os
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle, Circle  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, 'backend', 'app.py')
OUT = os.path.join(ROOT, 'docs', 'figures', 'report')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_numbers as pn                         # noqa: E402

NUM = pn.NUM
ALERT_T = NUM['alert_threshold']                     # chat alert threshold (ablation JSON)

# ----------------------------------------------------------------------------- style
CM = 1 / 2.54
WIDTH = 15.0                     # cm; figures are placed at width=15cm (1:1)
FS = 9.0                         # body text, pt (the report's minimum)
FS_T = 9.5                       # box titles
FS_H = 10.0                      # panel / tier headers

INK = '#000000'
ORANGE = '#E07B1A'               # PES orange: the phones (data capture / presentation)
RUST = '#B95427'                 # PES rust: the server
GREY = '#6B6B6B'                 # managed services, data stores, baselines
LINE = '#3A3A3A'                 # arrows
NOTE = '#4D4D4D'                 # secondary text (still near-black for print)

plt.rcParams.update({
    'font.family': ['Arial', 'DejaVu Sans'],
    'font.size': FS,
    'axes.unicode_minus': False,
})


def tint(hex_color, t):
    """Blend a colour with white (t = share of the colour)."""
    h = hex_color.lstrip('#')
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return '#%02X%02X%02X' % tuple(round(c * t + 255 * (1 - t)) for c in rgb)


PHONE = {'ec': ORANGE, 'fc': tint(ORANGE, 0.13)}
SERVER = {'ec': RUST, 'fc': tint(RUST, 0.12)}
EXTERNAL = {'ec': GREY, 'fc': tint(GREY, 0.10)}
FRAME_PHONE = {'ec': ORANGE, 'fc': tint(ORANGE, 0.05)}
FRAME_SERVER = {'ec': RUST, 'fc': tint(RUST, 0.05)}
FRAME_EXT = {'ec': GREY, 'fc': tint(GREY, 0.04)}


def lh(fs):
    """Line height in cm for a font size in pt."""
    return fs * 1.25 / 72 * 2.54


# ------------------------------------------------------------------ facts from code
def read_app():
    with open(APP, encoding='utf-8') as f:
        return f.read()


def read_schema():
    """Tables -> ordered column list, and declared foreign keys, from init_db()."""
    src = read_app()
    m = re.search(r"def init_db\(\):(.*?)\ninit_db\(\)", src, re.S)
    body = m.group(1) if m else src
    tables, fks = {}, []
    for tm in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\s*\);", body, re.S):
        name, cols = tm.group(1), tm.group(2)
        tables[name] = []
        for raw in cols.split('\n'):
            line = raw.strip()
            if not line or line.startswith('--'):
                continue
            fk = re.match(r"FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)", line)
            if fk:
                fks.append((name, fk.group(1), fk.group(2)))
                continue
            cm = re.match(r"(\w+)\s+[A-Z]", line)
            if cm:
                tables[name].append(cm.group(1))
    for am in re.finditer(r"add_column\(c,\s*'(\w+)',\s*'(\w+)'", body):
        t, col = am.groups()
        cols = tables.setdefault(t, [])
        if col not in cols:
            cols.append(col)
    return tables, fks


def count_operations():
    """Number of (path, method) operations declared with @app.route."""
    n = 0
    for m in re.finditer(r"@app\.route\(\s*'[^']+'\s*(?:,\s*methods=\[([^\]]*)\])?\s*\)",
                         read_app()):
        n += len(re.findall(r"'(\w+)'", m.group(1))) if m.group(1) else 1
    return n


TABLES, FKS = read_schema()
N_OPS = count_operations()

# --------------------------------------------------------------------- primitives
_BOXED = []          # (text artist, (x0, y0, x1, y1)) for the overflow check


def canvas(h_cm):
    fig = plt.figure(figsize=(WIDTH * CM, h_cm * CM), dpi=200)
    fig.patch.set_facecolor('white')
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(0, h_cm)
    ax.axis('off')
    _BOXED.clear()
    return fig, ax


def rbox(ax, x, y, w, h, style, lw=1.1, ls='-', radius=0.10, z=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f'round,pad=0,rounding_size={radius}',
                                fc=style['fc'], ec=style['ec'], lw=lw, ls=ls, zorder=z))


def box(ax, x, y, w, h, title=None, lines=(), style=SERVER, align='center', lw=1.1,
        ls='-', title_fs=FS_T, fs=FS, radius=0.10, pad_x=0.14, z=2):
    """Rounded box with a bold title and body lines, block centred vertically.
    A body line may be a (text, 'note') tuple: rendered italic in secondary ink."""
    rbox(ax, x, y, w, h, style, lw=lw, ls=ls, radius=radius, z=z)
    rows = []
    if title:
        rows.append((title, title_fs, 'bold', 'normal', INK))
    for ln in lines:
        if isinstance(ln, tuple):
            rows.append((ln[0], fs, 'normal', 'italic', NOTE))
        else:
            rows.append((ln, fs, 'normal', 'normal', INK))
    heights = [lh(r[1]) for r in rows]
    cy = y + h / 2 + sum(heights) / 2
    tx = x + w / 2 if align == 'center' else x + pad_x
    for (txt, size, weight, style_, color), hh in zip(rows, heights):
        cy -= hh
        t = ax.text(tx, cy + hh / 2, txt, fontsize=size, fontweight=weight,
                    fontstyle=style_, color=color, ha=align, va='center', zorder=z + 1)
        _BOXED.append((t, (x, y, x + w, y + h)))


def head(ax, p_from, p_to, color=LINE, z=3, size=1.0):
    dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    hl, hw = 0.20 * size, 0.075 * size
    bx, by = p_to[0] - ux * hl, p_to[1] - uy * hl
    px, py = -uy, ux
    ax.add_patch(Polygon([p_to, (bx + px * hw, by + py * hw), (bx - px * hw, by - py * hw)],
                         closed=True, fc=color, ec=color, lw=0.4, zorder=z + 0.1))
    return (bx, by)


def arrow(ax, pts, color=LINE, lw=1.0, ls='-', end=True, start=False, z=3):
    """Poly-line with filled arrow head(s); dashed lines keep solid heads."""
    pts = [tuple(p) for p in pts]
    draw = list(pts)
    if end:
        draw[-1] = head(ax, pts[-2], pts[-1], color, z)
    if start:
        draw[0] = head(ax, pts[1], pts[0], color, z)
    xs, ys = zip(*draw)
    dash = (0, (4.5, 3)) if ls == '--' else ls
    ax.plot(xs, ys, color=color, lw=lw, ls=dash, solid_capstyle='butt',
            dash_capstyle='butt', zorder=z)


def label(ax, x, y, s, fs=FS, ha='center', va='center', color=INK, bg='white',
          weight='normal', style='normal', z=5):
    return ax.text(x, y, s, fontsize=fs, ha=ha, va=va, color=color, fontweight=weight,
                   fontstyle=style, zorder=z,
                   bbox=dict(fc=bg, ec='none', pad=0.6) if bg else None)


def marker(ax, x, y, n, z=6):
    ax.add_patch(Circle((x, y), 0.19, fc=INK, ec='white', lw=0.8, zorder=z))
    ax.text(x, y - 0.005, str(n), fontsize=FS, fontweight='bold', color='white',
            ha='center', va='center', zorder=z + 1)


def check(fig, ax, name):
    """Warn about text that overflows its box or collides with other text."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    to_px = ax.transData
    tol = 1.0
    for t, (x0, y0, x1, y1) in _BOXED:
        bb = t.get_window_extent(r)
        (X0, Y0), (X1, Y1) = to_px.transform([(x0, y0), (x1, y1)])
        if bb.x0 < X0 - tol or bb.x1 > X1 + tol or bb.y0 < Y0 - tol or bb.y1 > Y1 + tol:
            print(f'  WARN {name}: text overflows its box: {t.get_text()!r}')
    texts = [t for t in ax.texts if t.get_text().strip()]
    boxes = [t.get_window_extent(r).expanded(1.0, 0.92) for t in texts]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = boxes[i], boxes[j]
            ox = min(a.x1, b.x1) - max(a.x0, b.x0)
            oy = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ox > 2 and oy > 2:
                print(f'  WARN {name}: text collision: {texts[i].get_text()!r} '
                      f'<> {texts[j].get_text()!r}')
    sizes = {round(t.get_fontsize(), 2) for t in ax.texts}
    if min(sizes) < FS:
        print(f'  WARN {name}: text below {FS} pt: {sorted(sizes)}')


def save(fig, ax, name):
    check(fig, ax, name)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f'ch5_{name}.png')
    fig.savefig(path, dpi=200, facecolor='white')
    plt.close(fig)
    print('wrote', os.path.relpath(path, ROOT))


# ===================================================================== Figure 5.1
def fig_architecture():
    H = 12.6
    fig, ax = canvas(H)
    cols = [(0.25, FRAME_PHONE, PHONE, 'Data-collection tier', 'Child app (Android, Kotlin)'),
            (5.40, FRAME_SERVER, SERVER, 'Serving tier', 'Flask backend on Render'),
            (10.55, FRAME_PHONE, PHONE, 'Presentation tier', 'Parent app (Android, Kotlin)')]
    fw, fy0, fy1 = 4.2, 3.25, 12.35
    comps = {
        0: [('Session monitor', 'finds the game in front,', 'starts and ends sessions'),
            ('Typed-chat capture', 'own keyboard (IME) and', 'accessibility service'),
            ('Voice capture', 'speech-to-text on phone,', '10 s clips for tone'),
            ('Health and events', 'heartbeat every 3 min,', 'screen, notifications'),
            ('Offline queues', 'chat lines and offline', 'sessions, retried later')],
        1: [('REST API', f'{N_OPS} operations, JSON,', 'rate limits per client'),
            ('Guards', 'signed token, parent role,', 'current consent'),
            ('Scoring engine', 'behaviour, chat and voice', 'models, fusion, band'),
            ('Alerts and push', 'alert rows; FCM push', 'for urgent events'),
            ('Data layer', 'same SQL on SQLite', 'and PostgreSQL; pooled')],
        2: [('Dashboard', 'concern band, reasons,', 'trend, live status'),
            ('Alerts', 'feed with Accurate /', 'False-alarm verdicts'),
            ('Insights', 'emotions, chat view,', 'weekly PDF report'),
            ('Controls', 'nudges, daily limit,', 'data deletion'),
            ('Delivery', 'polls alerts every 25 s,', 'receives FCM push')],
    }
    bh, gap, top = 1.40, 0.18, 11.05
    ys = [top - bh - i * (bh + gap) for i in range(5)]
    for ci, (x, fstyle, bstyle, t1, t2) in enumerate(cols):
        rbox(ax, x, fy0, fw, fy1 - fy0, fstyle, lw=1.3, radius=0.16, z=1)
        ax.text(x + fw / 2, 11.92, t1, fontsize=FS_H, fontweight='bold', ha='center',
                va='center', zorder=3)
        ax.text(x + fw / 2, 11.48, t2, fontsize=FS, ha='center', va='center', zorder=3)
        for i, (tt, l1, l2) in enumerate(comps[ci]):
            box(ax, x + 0.15, ys[i], fw - 0.30, bh, tt, [l1, l2], style=bstyle)

    # bottom row: local store, database, push service
    by0, bh2 = 1.40, 1.30
    box(ax, 0.25, by0, fw, bh2, 'Encrypted local store',
        ['token and queued items'], style=PHONE)
    box(ax, 5.40, by0, fw, bh2, 'Neon PostgreSQL',
        [f'{len(TABLES)} tables, serverless'], style=EXTERNAL)
    box(ax, 10.55, by0, fw, bh2, 'Firebase (FCM)',
        ['data-only push messages'], style=EXTERNAL)

    # 1/2: child <-> API ; 3: parent <-> API
    y_api = ys[0] + bh / 2
    arrow(ax, [(4.45, y_api + 0.30), (5.55, y_api + 0.30)])
    marker(ax, 5.0, y_api + 0.30, 1)
    arrow(ax, [(5.55, y_api - 0.30), (4.45, y_api - 0.30)])
    marker(ax, 5.0, y_api - 0.30, 2)
    arrow(ax, [(10.55, y_api), (9.45, y_api)], start=True)
    marker(ax, 10.0, y_api, 3)
    # 4: data layer <-> database
    arrow(ax, [(7.5, fy0), (7.5, by0 + bh2)], start=True)
    marker(ax, 7.95, (fy0 + by0 + bh2) / 2, 4)
    # 5: alerts -> FCM -> parent delivery
    y_alert = ys[3] + bh / 2
    arrow(ax, [(9.45, y_alert), (10.0, y_alert), (10.0, by0 + bh2 / 2),
               (10.55, by0 + bh2 / 2)])
    marker(ax, 10.0, (y_alert + by0 + bh2 / 2) / 2, 5)
    arrow(ax, [(12.65, by0 + bh2), (12.65, ys[4])])
    # 6: phone <-> local store
    arrow(ax, [(2.35, fy0), (2.35, by0 + bh2)], start=True)
    marker(ax, 2.8, (fy0 + by0 + bh2) / 2, 6)

    legend = [(1, 'child uploads: sessions, chat, audio'), (2, 'child polls nudges and limits'),
              (3, 'parent views, verdicts, nudges'), (4, 'SQL over TLS'),
              (5, 'push for urgent alerts'), (6, 'encrypted on-device storage')]
    for k, (n, s) in enumerate(legend):       # two columns of three rows
        lx = 0.45 + (k // 3) * 7.50
        ly = 1.08 - (k % 3) * 0.40
        marker(ax, lx, ly, n)
        ax.text(lx + 0.32, ly, s, fontsize=FS, ha='left', va='center', zorder=3)
    save(fig, ax, 'architecture')


# ===================================================================== Figure 5.2
def fig_deployment():
    H = 12.8
    fig, ax = canvas(H)
    # GitHub band
    rbox(ax, 0.25, 9.35, 14.5, 3.20, FRAME_EXT, lw=1.3, radius=0.16, z=1)
    ax.text(0.45, 12.25, 'GitHub', fontsize=FS_H, fontweight='bold', ha='left',
            va='center', zorder=3)
    box(ax, 0.45, 9.55, 3.8, 2.30, 'Releases',
        ['signed ChildApp and', 'ParentApp APKs'], style=EXTERNAL)
    box(ax, 5.60, 9.55, 3.8, 2.30, 'Repository (main)',
        ['backend, both apps,', 'models, docs, workflows'], style=EXTERNAL)
    box(ax, 10.75, 9.55, 3.8, 2.30, 'Actions workflows',
        ['CI: every push and PR', 'drift check: weekly', 'keep-warm ping: manual',
         'pilot report: manual'], style=EXTERNAL)

    box(ax, 0.25, 5.65, 3.8, 2.95, 'Child phone',
        ['ChildApp, sideloaded', 'Vosk model on device', 'encrypted local store',
         'Android 8.0 or later'], style=PHONE)
    box(ax, 0.25, 1.65, 3.8, 2.95, 'Parent phones',
        ['ParentApp on each', "guardian's phone", 'one FCM token per', 'device'],
        style=PHONE)
    box(ax, 5.35, 1.65, 4.3, 6.95, 'Render web service',
        ['free plan, Singapore region',
         'Docker image on', 'python:3.11-slim',
         'gunicorn: 1 worker, 4 threads', 'Flask app + model files',
         'health check: /api/health', '',
         'environment variables:', 'AUTH_SECRET and', 'PIN_PEPPER (generated);',
         'DATABASE_URL and', 'Firebase key (by hand);',
         'AUTH_ENFORCE=1,', 'KEEP_AUDIO=0'],
        style=SERVER)
    box(ax, 10.75, 5.65, 4.0, 2.95, 'Neon PostgreSQL',
        ['serverless; scales to', 'zero when idle', 'pool of up to 10',
         'validated connections'], style=EXTERNAL)
    box(ax, 10.75, 1.65, 4.0, 2.95, 'Firebase Cloud',
        ['Messaging (FCM)', 'data-only messages', 'to every guardian', 'device of the family'],
        style=EXTERNAL)

    for y, txt in ((7.15, 'HTTPS'), (3.15, 'HTTPS')):
        arrow(ax, [(4.05, y), (5.35, y)], start=True)
        label(ax, 4.70, y + 0.30, txt)
    arrow(ax, [(9.65, 7.15), (10.75, 7.15)], start=True)
    label(ax, 10.2, 7.45, 'TLS')
    arrow(ax, [(9.65, 3.15), (10.75, 3.15)])
    label(ax, 10.2, 3.45, 'send')
    arrow(ax, [(12.75, 1.65), (12.75, 0.75), (2.15, 0.75), (2.15, 1.65)])
    label(ax, 7.5, 0.75, 'push notification to the Parent app')
    for x, txt, side in ((2.15, 'sideload', 'left'), (7.5, 'auto-deploy', 'left'),
                         (12.75, 'drift check reads', 'right')):
        arrow(ax, [(x, 9.55), (x, 8.60)])
        label(ax, x + (0.15 if side == 'left' else -0.15), 9.08, txt, ha=side, bg=None)
    save(fig, ax, 'deployment')


# ===================================================================== Figure 5.3
def fig_dataflow():
    H = 12.6
    fig, ax = canvas(H)
    cx = [0.25, 3.90, 7.55]           # channel columns (w 3.3)
    cw = 3.30
    px, pw = 11.45, 3.30              # parent-side column
    heads = ['Session timing', 'Voice tone', 'Typed and spoken chat']
    for x, t in zip(cx, heads):
        ax.text(x + cw / 2, 12.25, t, fontsize=FS_H, fontweight='bold', ha='center',
                va='center')
    ax.text(px + pw / 2, 12.25, 'Parent side', fontsize=FS_H, fontweight='bold',
            ha='center', va='center')

    r1, r1h = 9.95, 1.85     # capture on the phone
    r2, r2h = 7.05, 2.30     # per item, on arrival
    r3, r3h = 5.00, 1.55     # channel score at session end
    box(ax, cx[0], r1, cw, r1h, 'Foreground game', ['UsageStats every 5 s;',
                                                    'ends after a', 'grace period'],
        style=PHONE)
    box(ax, cx[1], r1, cw, r1h, '10 s audio clip', ['16 kHz; dropped on', 'the phone if the',
                                                   'game is not in front'],
        style=PHONE)
    box(ax, cx[2], r1, cw, r1h, 'Chat lines', ['typed: keyboard or', 'accessibility; spoken:',
                                              'Vosk on the phone'], style=PHONE)
    # consent / token gate strip
    rbox(ax, 0.25, 9.38, 10.60, 0.42, {'ec': GREY, 'fc': 'white'}, lw=0.9, ls='--',
         radius=0.05, z=1)
    label(ax, 5.55, 9.59, 'server checks: signed token, ownership, current consent',
          bg='white', z=4)

    box(ax, cx[0], r2, cw, r2h, 'Session row', ['start, end, duration', ('→ sessions', 'note')])
    box(ax, cx[1], r2, cw, r2h, 'Tone analysis', ['speech gate, features,',
                                                 'emotion and word', 'valence; WAV deleted',
                                                 ('→ voice_events', 'note')])
    box(ax, cx[2], r2, cw, r2h, 'Line toxicity', ['noisy-OR of keyword', 'and model scores',
                                                 ('→ chat_messages', 'note')])
    box(ax, cx[0], r3, cw, r3h, 'Behaviour score b', ['10 features, 30-day', 'history, RF'])
    box(ax, cx[1], r3, cw, r3h, 'Voice score v', ['mean risk of the', "session's emotions"])
    box(ax, cx[2], r3, cw, r3h, 'Chat score c', ['maximum typed line', '(spoken excluded)'])

    fz, fh = 2.98, 1.72
    box(ax, 0.25, fz, 10.60, fh, 'Fusion at session end',
        ['weighted mean of the channels present (0.40 / 0.30 / 0.30, renormalised)',
         '→ Low, Some or High concern; no High before 3 scored sessions',
         ('→ predictions, with the score version', 'note')])

    # parent side column
    box(ax, px, 6.75, pw, 2.85, 'Alerts', [f'line ≥ {ALERT_T} or a', 'streak: at once;',
                                          'Some / High concern:', 'at session end',
                                          ('→ alerts', 'note')], style=EXTERNAL)
    box(ax, px, 4.55, pw, 1.75, 'Delivery', ['app polls every 25 s;', 'FCM push if urgent'],
        style=EXTERNAL)
    box(ax, px, 2.40, pw, 1.70, 'Parent app', ['band and reasons;', 'rates each alert'],
        style=EXTERNAL)
    box(ax, px, 0.25, pw, 1.70, 'Feedback loop', ['tuning script proposes,',
                                                 'a person applies',
                                                 ('→ feedback', 'note')], style=EXTERNAL)

    for x in cx:
        arrow(ax, [(x + cw / 2, r1), (x + cw / 2, r2 + r2h)])
    for x in cx:
        arrow(ax, [(x + cw / 2, r2), (x + cw / 2, r3 + r3h)])
        arrow(ax, [(x + cw / 2, r3), (x + cw / 2, fz + fh)])
    # spoken words give the voice channel its valence (chat -> tone, same row)
    arrow(ax, [(cx[2], r2 + 0.55), (cx[1] + cw, r2 + 0.55)])
    # immediate chat alert
    arrow(ax, [(cx[2] + cw, r2 + r2h - 0.55), (px, r2 + r2h - 0.55)])
    # fusion -> alerts
    arrow(ax, [(10.85, fz + fh / 2), (11.15, fz + fh / 2), (11.15, 7.25), (px, 7.25)])
    for y0, y1 in ((6.75, 6.30), (4.55, 4.10), (2.40, 1.95)):
        arrow(ax, [(px + pw / 2, y0), (px + pw / 2, y1)])

    # legend
    lx, ly = 0.35, 2.55
    for sx, st, txt in ((0.0, PHONE, "on the child's phone"), (3.50, SERVER, 'on the server'),
                        (6.60, EXTERNAL, 'parent side, offline tools')):
        rbox(ax, lx + sx, ly - 0.17, 0.42, 0.34, st, lw=1.0, radius=0.05)
        ax.text(lx + sx + 0.55, ly, txt, fontsize=FS, ha='left', va='center')
    ax.text(lx, 1.95, '→ name: the database table that keeps the result (italic)',
            fontsize=FS, ha='left', va='center', color=NOTE, fontstyle='italic')
    ax.text(lx, 1.45, 'Raw audio and text outside the tracked game never reach a table.',
            fontsize=FS, ha='left', va='center')
    ax.text(lx, 0.95, 'Spoken lines feed the voice valence and the alert check,',
            fontsize=FS, ha='left', va='center')
    ax.text(lx, 0.55, 'but not the chat score c (no double counting).',
            fontsize=FS, ha='left', va='center')
    save(fig, ax, 'dataflow')


# ===================================================================== Figure 5.4
ER_COLS = {
    'users': ['user_id', 'name', 'age', 'family_code', 'pin_hash', 'parent_pin_hash',
              'consent_given_at', 'consent_version', 'auth_version',
              'family_auth_version', 'last_seen', 'tz_offset_min'],
    'guardian_devices': ['id', 'family_code', 'fcm_token'],
    'sessions': ['session_id', 'user_id', 'game_name', 'start_time', 'end_time',
                 'duration_seconds', 'final_risk_score', 'risk_category', 'client_key',
                 'finalization_complete', 'voice_rescore_pending'],
    'behavioral_data': ['id', 'session_id', '#10 features', '#10 derived scores'],
    'chat_messages': ['id', 'session_id', 'message', 'source', 'confidence'],
    'voice_events': ['id', 'session_id', 'emotion', 'intensity', 'capture_valid', 'probs'],
    'predictions': ['id', 'session_id', 'behavior_score', 'chat_score', 'voice_score',
                    'final_risk_score', 'risk_category', '#3 *_present flags',
                    'score_version'],
    'alerts': ['id', 'user_id', 'session_id', 'type', 'severity'],
    'feedback': ['id', 'user_id', 'alert_id', 'prediction_id', 'label'],
    'child_nudges': ['id', 'user_id', 'kind, delivered'],
    'screen_events': ['user_id', 'event_type'],
    'notification_events': ['user_id', 'notification_title'],
    'reflections': ['user_id', 'mood_rating'],
    'counselor_messages': ['user_id', 'role, content'],
    'anomalies': ['user_id', 'kind, z_score'],
    'streaks': ['user_id', 'current_streak'],
    'time_limits': ['user_id', 'daily_limit_hours'],
}
ER_TAGS = {('users', 'user_id'): 'PK', ('guardian_devices', 'id'): 'PK',
           ('guardian_devices', 'fcm_token'): 'UQ', ('sessions', 'session_id'): 'PK',
           ('sessions', 'user_id'): 'FK', ('feedback', 'alert_id'): 'UQ',
           ('streaks', 'user_id'): 'PK', ('time_limits', 'user_id'): 'PK'}
for _t in ('behavioral_data', 'chat_messages', 'voice_events', 'predictions'):
    ER_TAGS[(_t, 'session_id')] = 'FK'
for _t in ('behavioral_data', 'chat_messages', 'voice_events', 'predictions', 'alerts',
           'feedback', 'child_nudges'):
    ER_TAGS[(_t, 'id')] = 'PK'


def er_rows(table):
    """Columns to draw for a table, keeping only names that exist in init_db()."""
    have = set(TABLES.get(table, []))
    rows = []
    for col in ER_COLS[table]:
        if col.startswith('#'):
            rows.append((col[1:], None, True))
            continue
        names = [c.strip() for c in col.split(',')]
        missing = [c for c in names if c not in have]
        if missing:
            print(f'  NOTE er: {table}.{"/".join(missing)} not in backend/app.py yet - omitted')
            continue
        rows.append((col, ER_TAGS.get((table, col)), False))
    return rows


def er_table(ax, x, y_top, w, table, scope):
    style = {'child': PHONE, 'session': SERVER, 'family': EXTERNAL}[scope]
    rows = er_rows(table)
    hh, rh = 0.50, lh(FS)
    h = hh + len(rows) * rh + 0.14
    y0 = y_top - h
    ax.add_patch(Rectangle((x, y0), w, h, fc='white', ec=style['ec'], lw=1.1, zorder=2))
    ax.add_patch(Rectangle((x, y_top - hh), w, hh, fc=style['fc'], ec=style['ec'], lw=1.1,
                           zorder=2))
    t = ax.text(x + 0.12, y_top - hh / 2, table, fontsize=FS_T, fontweight='bold',
                ha='left', va='center', zorder=3)
    _BOXED.append((t, (x, y_top - hh, x + w, y_top)))
    cy = y_top - hh - 0.07
    for name, tag, summary in rows:
        cy -= rh
        t = ax.text(x + 0.12, cy + rh / 2, name, fontsize=FS, ha='left', va='center',
                    fontstyle='italic' if summary else 'normal',
                    color=NOTE if summary else INK, zorder=3)
        _BOXED.append((t, (x, y0, x + w - (0.45 if tag else 0), y_top)))
        if tag:
            ax.text(x + w - 0.10, cy + rh / 2, tag, fontsize=FS, ha='right', va='center',
                    color=NOTE, fontweight='bold', zorder=3)
    return (x, y0, x + w, y_top)


def card(ax, x, y, s, ha='center'):
    ax.text(x, y, s, fontsize=FS, ha=ha, va='center', zorder=6,
            bbox=dict(fc='white', ec='none', pad=0.3))


def fig_er():
    H = 14.3
    fig, ax = canvas(H)
    top = 14.05
    c1, c2, c3, c4 = 0.20, 4.25, 7.80, 11.75       # 0.50 cm gaps carry the buses
    w1, w2, w3, w4 = 3.55, 3.05, 3.45, 3.00
    # column 1: per-child event and setting tables
    col1 = ['screen_events', 'notification_events', 'reflections', 'counselor_messages',
            'anomalies', 'streaks', 'time_limits']
    b1, y = {}, top
    for t in col1:
        b1[t] = er_table(ax, c1, y, w1, t, 'child')
        y = b1[t][1] - 0.20
    # column 2
    users = er_table(ax, c2, top, w2, 'users', 'child')
    gdev = er_table(ax, c2, users[1] - 0.75, w2, 'guardian_devices', 'family')
    # column 3
    sess = er_table(ax, c3, top, w3, 'sessions', 'session')
    alerts = er_table(ax, c3, sess[1] - 0.55, w3, 'alerts', 'child')
    fb = er_table(ax, c3, alerts[1] - 0.45, w3, 'feedback', 'child')
    nud = er_table(ax, c3, fb[1] - 0.30, w3, 'child_nudges', 'child')
    # column 4
    b4, y = {}, top
    for t in ('behavioral_data', 'chat_messages', 'voice_events', 'predictions'):
        b4[t] = er_table(ax, c4, y, w4, t, 'session')
        y = b4[t][1] - 0.28

    declared = {(a, b) for a, _, b in FKS}
    solid = '-'

    # users 1 - N sessions (declared FK)
    ys = top - 1.15
    arrow(ax, [(users[2], ys), (sess[0], ys)], end=False,
          ls=solid if ('sessions', 'users') in declared else '--')
    card(ax, users[2] + 0.13, ys + 0.22, '1')
    card(ax, sess[0] - 0.13, ys + 0.22, 'N')

    # sessions 1 - N evidence tables (declared FKs), bus in the c3/c4 gap
    bus = (sess[2] + c4) / 2
    tgt = [(b4['behavioral_data'], ys)] + [(b4[t], (b4[t][1] + b4[t][3]) / 2 + 0.25)
                                           for t in ('chat_messages', 'voice_events')]
    tgt.append((b4['predictions'], b4['predictions'][3] - 0.75))
    arrow(ax, [(sess[2], ys), (bus, ys)], end=False)
    arrow(ax, [(bus, ys), (bus, tgt[-1][1])], end=False)
    card(ax, sess[2] + 0.12, ys + 0.22, '1')
    for bx, yy in tgt:
        arrow(ax, [(bus, yy), (bx[0], yy)], end=False)
        card(ax, bx[0] - 0.12, yy + 0.22, 'N')

    # users - per-child tables in column 1 (logical references), bus in c1/c2 gap
    bus1 = (c1 + w1 + c2) / 2
    ystub = users[1] + 1.0
    arrow(ax, [(users[0], ystub), (bus1, ystub)], end=False, ls='--')
    card(ax, users[0] - 0.12, ystub + 0.22, '1')
    centers = [((b[1] + b[3]) / 2, t) for t, b in b1.items()]
    arrow(ax, [(bus1, max(c for c, _ in centers + [(ystub, '')])),
               (bus1, min(c for c, _ in centers))], end=False, ls='--')
    for cyy, t in centers:
        arrow(ax, [(bus1, cyy), (c1 + w1, cyy)], end=False, ls='--')
        card(ax, c1 + w1 + 0.12, cyy + 0.22, '1' if t in ('streaks', 'time_limits') else 'N')

    # users - alerts / feedback / child_nudges (logical), bus in c2/c3 gap
    bus2 = (c2 + w2 + c3) / 2
    ystub2 = users[1] + 0.35
    arrow(ax, [(users[2], ystub2), (bus2, ystub2)], end=False, ls='--')
    card(ax, users[2] + 0.13, ystub2 + 0.22, '1')
    y_al = alerts[1] + 0.55
    y_fb = fb[1] + 0.95
    y_nu = (nud[1] + nud[3]) / 2
    arrow(ax, [(bus2, ystub2), (bus2, y_nu)], end=False, ls='--')
    for yy in (y_al, y_fb, y_nu):
        arrow(ax, [(bus2, yy), (c3, yy)], end=False, ls='--')
        card(ax, c3 - 0.12, yy + 0.22, 'N')

    # sessions 0..1 - N alerts ; alerts 1 - 0..1 feedback ; feedback N - 1 predictions
    xm = c3 + w3 * 0.72
    arrow(ax, [(xm, sess[1]), (xm, alerts[3])], end=False, ls='--')
    card(ax, xm + 0.16, sess[1] - 0.14, '1', ha='left')
    card(ax, xm + 0.16, alerts[3] + 0.16, 'N', ha='left')
    arrow(ax, [(xm, alerts[1]), (xm, fb[3])], end=False, ls='--')
    card(ax, xm - 0.16, (alerts[1] + fb[3]) / 2, '1', ha='right')
    card(ax, xm + 0.16, (alerts[1] + fb[3]) / 2, '0..1', ha='left')
    yfp = fb[1] + 0.40
    arrow(ax, [(fb[2], yfp), (c4, yfp)], end=False, ls='--')
    card(ax, fb[2] + 0.14, yfp + 0.22, 'N')
    card(ax, c4 - 0.12, yfp + 0.22, '1')

    # users N - N guardian_devices through the shared family_code value
    xg = c2 + 0.30
    arrow(ax, [(xg, users[1]), (xg, gdev[3])], end=False, ls='--')
    ax.text(xg + 0.15, (users[1] + gdev[3]) / 2, 'shared family_code', fontsize=FS,
            ha='left', va='center', zorder=3)

    # legend in the free space under guardian_devices
    lx, ly = c2 + 0.05, gdev[1] - 0.55
    ax.text(lx, ly, 'Legend', fontsize=FS_T, fontweight='bold', ha='left', va='center')
    arrow(ax, [(lx, ly - 0.50), (lx + 0.60, ly - 0.50)], end=False)
    ax.text(lx + 0.75, ly - 0.50, 'declared FK', fontsize=FS, ha='left', va='center')
    arrow(ax, [(lx, ly - 0.95), (lx + 0.60, ly - 0.95)], end=False, ls='--')
    ax.text(lx + 0.75, ly - 0.95, 'checked by API', fontsize=FS, ha='left', va='center')
    ax.text(lx, ly - 1.40, '1, N, 0..1  cardinality', fontsize=FS, ha='left', va='center')
    ax.text(lx, ly - 1.80, 'PK primary key', fontsize=FS, ha='left', va='center')
    ax.text(lx, ly - 2.20, 'FK foreign key', fontsize=FS, ha='left', va='center')
    ax.text(lx, ly - 2.60, 'UQ unique index', fontsize=FS, ha='left', va='center')
    for k, (st, txt) in enumerate(((PHONE, 'per child'), (SERVER, 'per session'),
                                   (EXTERNAL, 'per family'))):
        yy = ly - 3.10 - k * 0.45
        ax.add_patch(Rectangle((lx, yy - 0.15), 0.6, 0.30, fc=st['fc'], ec=st['ec'],
                               lw=1.0, zorder=2))
        ax.text(lx + 0.9, yy, txt, fontsize=FS, ha='left', va='center')
    save(fig, ax, 'er')


# ============================================================ sequence diagrams
def lanes(ax, spec, top, bottom, w=1.95, h=0.90):
    X = {}
    for key, x, l1, l2, style in spec:
        box(ax, x - w / 2, top - h, w, h, l1, [l2] if l2 else [], style=style)
        ax.plot([x, x], [top - h, bottom], color=GREY, lw=0.8, ls=(0, (3, 3)), zorder=0.5)
        X[key] = x
    return X


def msg(ax, X, a, b, y, text, ret=False, dx=0.0):
    arrow(ax, [(X[a], y), (X[b], y)], ls='--' if ret else '-')
    label(ax, (X[a] + X[b]) / 2 + dx, y + 0.21, text)


def self_msg(ax, X, who, y, text, side='right'):
    x = X[who]
    s = 1 if side == 'right' else -1
    arrow(ax, [(x, y + 0.13), (x + s * 0.38, y + 0.13), (x + s * 0.38, y - 0.13),
               (x, y - 0.13)])
    label(ax, x + s * 0.50, y, text, ha='left' if s > 0 else 'right')


def fragment(ax, x0, x1, y0, y1, kind, cond):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc='none', ec=GREY, lw=0.9,
                           zorder=1))
    t = ax.text(x0 + 0.08, y1 - 0.21, kind, fontsize=FS, fontweight='bold', ha='left',
                va='center', zorder=6, bbox=dict(fc='white', ec=GREY, lw=0.8, pad=1.2))
    ax.text(x0 + 0.62 + 0.09 * len(kind), y1 - 0.21, cond, fontsize=FS, ha='left',
            va='center', zorder=6, color=NOTE, fontstyle='italic',
            bbox=dict(fc='white', ec='none', pad=0.4))
    return t


def fig_seq_session():
    H = 14.8
    fig, ax = canvas(H)
    spec = [('child', 1.10, 'Child app', '(monitor)', PHONE),
            ('cap', 3.15, 'Capture', 'services', PHONE),
            ('api', 5.35, 'Flask API', 'guards', SERVER),
            ('score', 7.55, 'Scoring', 'engine', SERVER),
            ('db', 9.75, 'Database', '(Neon)', EXTERNAL),
            ('fcm', 11.85, 'FCM', '', EXTERNAL),
            ('parent', 13.90, 'Parent', 'app', PHONE)]
    X = lanes(ax, spec, top=14.65, bottom=0.25)
    y = 13.20
    self_msg(ax, X, 'child', y, 'game in front (5 s check)')
    y -= 0.62
    msg(ax, X, 'child', 'api', y, 'POST /session/start')
    y -= 0.62
    msg(ax, X, 'api', 'db', y, 'token + consent; open session row')
    y -= 0.62
    msg(ax, X, 'api', 'child', y, 'session_id', ret=True)
    y -= 0.62
    msg(ax, X, 'child', 'cap', y, 'start capture')
    loop_top = y - 0.30
    y -= 1.05
    msg(ax, X, 'cap', 'api', y, 'POST chat line', dx=-0.15)
    y -= 0.62
    msg(ax, X, 'api', 'score', y, 'noisy-OR line score')
    y -= 0.62
    msg(ax, X, 'score', 'db', y, f'store; alert if ≥ {ALERT_T}')
    y -= 0.62
    msg(ax, X, 'cap', 'api', y, 'POST 10 s WAV', dx=-0.15)
    y -= 0.62
    msg(ax, X, 'api', 'score', y, 'gate, features, emotion')
    y -= 0.62
    msg(ax, X, 'score', 'db', y, 'store emotion; WAV deleted')
    fragment(ax, 2.20, 10.95, y - 0.30, loop_top, 'loop', 'while the game is in front')
    y -= 0.95
    self_msg(ax, X, 'child', y, 'away from game > 20 s')
    y -= 0.62
    msg(ax, X, 'child', 'api', y, 'POST /session/<sid>/end')
    y -= 0.62
    msg(ax, X, 'api', 'score', y, 'finalise: features, fusion')
    y -= 0.62
    msg(ax, X, 'score', 'db', y, 'prediction + concern alert')
    opt_top = y - 0.30
    y -= 1.05
    msg(ax, X, 'api', 'fcm', y, 'push to every guardian device')
    y -= 0.62
    msg(ax, X, 'fcm', 'parent', y, 'notification')
    fragment(ax, 4.40, 14.85, y - 0.30, opt_top, 'opt', 'High concern')
    y -= 0.95
    msg(ax, X, 'parent', 'api', y, 'GET /api/alerts (every 25 s)')
    y -= 0.62
    msg(ax, X, 'api', 'parent', y, 'alerts with severity', ret=True)
    save(fig, ax, 'seq_session')


def fig_seq_feedback():
    H = 14.4
    fig, ax = canvas(H)
    spec = [('parent', 1.45, 'Parent app', '(guardian phone)', PHONE),
            ('api', 4.60, 'Flask API', 'guards', SERVER),
            ('db', 7.75, 'Database', '(Neon)', EXTERNAL),
            ('child', 10.75, 'Child app', '(monitor)', PHONE),
            ('tune', 13.55, 'Tuning script', '(run by team)', EXTERNAL)]
    X = lanes(ax, spec, top=14.25, bottom=0.25, w=2.45)
    y = 12.30
    sec_top = y + 0.85
    self_msg(ax, X, 'parent', y, 'Accurate or False alarm')
    y -= 0.62
    msg(ax, X, 'parent', 'api', y, 'POST /api/feedback')
    y -= 0.62
    msg(ax, X, 'api', 'db', y, 'alert owner; parent role')
    y -= 0.62
    msg(ax, X, 'api', 'db', y, 'snapshot + upsert verdict')
    y -= 0.62
    msg(ax, X, 'api', 'parent', y, 'Feedback recorded', ret=True)
    y -= 0.62
    msg(ax, X, 'parent', 'api', y, 'GET /api/feedback/summary')
    y -= 0.62
    msg(ax, X, 'api', 'parent', y, 'agreement rate', ret=True)
    fragment(ax, 0.15, 9.15, y - 0.30, sec_top, 'verdict', 'one per alert')
    y -= 1.43
    sec_top = y + 0.85
    msg(ax, X, 'parent', 'api', y, 'POST /api/parent/nudge')
    y -= 0.62
    msg(ax, X, 'api', 'db', y, 'nudge row, delivered = 0')
    y -= 0.62
    msg(ax, X, 'child', 'api', y, 'GET /api/child/nudges (every 12 s)')
    y -= 0.62
    msg(ax, X, 'api', 'child', y, 'pending nudges', ret=True)
    y -= 0.62
    self_msg(ax, X, 'child', y, 'show notification', side='left')
    y -= 0.62
    msg(ax, X, 'child', 'api', y, 'POST /api/child/nudges/ack')
    y -= 0.62
    msg(ax, X, 'api', 'db', y, 'delivered = 1')
    fragment(ax, 0.15, 12.05, y - 0.30, sec_top, 'nudge', 'acknowledged after display')
    y -= 1.43
    sec_top = y + 0.85
    msg(ax, X, 'tune', 'db', y, 'read verdicts')
    y -= 0.62
    self_msg(ax, X, 'tune', y, 'Beta posterior', side='left')
    y -= 0.62
    self_msg(ax, X, 'tune', y, 'threshold_tuning.json', side='left')
    fragment(ax, 6.40, 14.85, y - 0.32, sec_top, 'offline', 'a person applies values')
    save(fig, ax, 'seq_feedback')


# ===================================================================== Figure 5.7
def state(ax, cx, cy, w, h, l1, l2=None, style=PHONE):
    box(ax, cx - w / 2, cy - h / 2, w, h, l1, [l2] if l2 else [], style=style,
        radius=0.22)
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def start_dot(ax, x, y):
    ax.add_patch(Circle((x, y), 0.11, fc=INK, ec=INK, zorder=4))


def panel(ax, y, text):
    ax.plot([0.2, 14.8], [y, y], color=GREY, lw=0.8, zorder=0.5)
    ax.text(0.25, y - 0.32, text, fontsize=FS_H, fontweight='bold', ha='left', va='center')


def fig_states():
    H = 15.2
    fig, ax = canvas(H)
    # ---------------- panel A: child app
    panel(ax, 15.05, 'A. Session on the child phone (PassiveMonitorService)')
    w, h = 2.45, 1.0
    yA, yA2 = 13.15, 10.95
    S0 = state(ax, 1.55, yA, w, h, 'No session', 'detecting')
    S1 = state(ax, 5.05, yA, w, h, 'Starting', 'request sent')
    S2 = state(ax, 8.55, yA, w, h, 'Open', 'game in front')
    S3 = state(ax, 12.55, yA, w, h, 'Grace', '20 s or 2 min')
    S4 = state(ax, 12.55, yA2, w, h, 'Ending', 'stop time saved')
    S5 = state(ax, 5.05, yA2, w, h, 'Offline marker', 'kept on disk')
    start_dot(ax, 0.40, yA + 0.85)
    arrow(ax, [(0.40, yA + 0.85), (0.40, yA + 0.25), (S0[0], yA + 0.25)])
    arrow(ax, [(S0[2], yA), (S1[0], yA)])
    label(ax, (S0[2] + S1[0]) / 2, yA + 0.74, 'game in front')
    arrow(ax, [(S1[2], yA), (S2[0], yA)])
    label(ax, (S1[2] + S2[0]) / 2, yA + 0.74, 'session_id')
    arrow(ax, [(S2[2], yA + 0.22), (S3[0], yA + 0.22)])
    label(ax, (S2[2] + S3[0]) / 2, yA + 0.74, 'game left')
    arrow(ax, [(S3[0], yA - 0.22), (S2[2], yA - 0.22)])
    label(ax, (S2[2] + S3[0]) / 2, yA - 0.76, 'returns in time')
    arrow(ax, [(12.55, S3[1]), (12.55, S4[3])])
    label(ax, 12.70, (S3[1] + S4[3]) / 2, 'grace over', ha='left', bg=None)
    arrow(ax, [(8.55, S2[1]), (8.55, yA2 + 0.22), (S4[0], yA2 + 0.22)])
    label(ax, (8.55 + S4[0]) / 2, yA2 + 0.48, 'another game')
    arrow(ax, [(5.05, S1[1]), (5.05, S5[3])])
    label(ax, 5.20, (S1[1] + S5[3]) / 2, 'network error', ha='left', bg=None)
    arrow(ax, [(S5[0], yA2), (1.55, yA2), (1.55, S0[1])])
    label(ax, 2.55, yA2 - 0.30, 'game left:', bg=None)
    label(ax, 2.55, yA2 - 0.68, 'queued for backfill', bg=None)
    arrow(ax, [(S4[0], yA2 - 0.22), (8.0, yA2 - 0.22), (8.0, 9.85), (0.85, 9.85),
               (0.85, S0[1])])
    label(ax, 5.05, 9.85, 'server confirms the end')
    arrow(ax, [(S4[2], yA2 + 0.15), (14.75, yA2 + 0.15), (14.75, yA2 - 0.25),
               (S4[2], yA2 - 0.25)])
    label(ax, 14.65, yA2 - 0.68, 'retry same stop time', ha='right', bg=None)

    # ---------------- panel B: server row
    panel(ax, 9.20, 'B. sessions row on the server (finalisation state)')
    yB, yB2 = 7.25, 5.15
    T0 = state(ax, 1.55, yB, w, h, 'Open', 'end_time empty', SERVER)
    T1 = state(ax, 5.30, yB, w, h, 'Closed', 'finalisation 0', SERVER)
    T2 = state(ax, 9.05, yB, w, h, 'Finalising', 'claimed, −1', SERVER)
    T3 = state(ax, 12.55, yB, w, h, 'Finalised', 'finalisation 1', SERVER)
    T4 = state(ax, 12.55, yB2, w, h, 'Re-score', 'pending', SERVER)
    start_dot(ax, 0.40, yB + 0.95)
    arrow(ax, [(0.40, yB + 0.95), (0.40, yB + 0.25), (T0[0], yB + 0.25)])
    label(ax, 0.55, yB + 1.20, 'POST /session/start', ha='left', bg=None)
    arrow(ax, [(T0[2], yB), (T1[0], yB)])
    label(ax, (T0[2] + T1[0]) / 2, yB + 0.74, 'end, next game or watchdog')
    arrow(ax, [(T1[2], yB + 0.22), (T2[0], yB + 0.22)])
    label(ax, (T1[2] + T2[0]) / 2, yB + 0.74, 'claim (lease)')
    arrow(ax, [(T2[0], yB - 0.22), (T1[2], yB - 0.22)])
    label(ax, (T1[2] + T2[0]) / 2, yB - 0.76, 'error: undo')
    arrow(ax, [(T2[2], yB), (T3[0], yB)])
    label(ax, (T2[2] + T3[0]) / 2, yB + 0.74, 'committed')
    arrow(ax, [(12.25, T3[1]), (12.25, T4[3])])
    label(ax, 12.10, (T3[1] + T4[3]) / 2, 'late chat or voice', ha='right', bg=None)
    arrow(ax, [(12.85, T4[3]), (12.85, T3[1])])
    label(ax, 13.00, (T3[1] + T4[3]) / 2, 're-scored', ha='left', bg=None)
    start_dot(ax, 5.30, yB2)
    arrow(ax, [(5.30 + 0.11, yB2), (6.1, yB2), (6.1, T1[1])])
    label(ax, 5.15, yB2 - 0.42, 'POST /session/backfill', ha='center', bg=None)

    # ---------------- panel C: keyboard layouts
    panel(ax, 4.20, 'C. Wellbeing Keyboard layouts (KeyboardLayoutMachine)')
    yC = 2.05
    hk = 0.80
    K1 = state(ax, 1.45, yC, 2.30, hk, 'SYMBOLS', None, PHONE)
    K0 = state(ax, 5.00, yC, 2.30, hk, 'QWERTY', None, PHONE)
    K2 = state(ax, 9.05, yC, 3.65, hk, 'DEVA_CONSONANTS', None, PHONE)
    K3 = state(ax, 13.30, yC, 2.85, hk, 'DEVA_VOWELS', None, PHONE)
    start_dot(ax, 5.00, 3.55)
    arrow(ax, [(5.00, 3.55), (5.00, K0[3])])
    label(ax, 5.15, 3.22, 'new input field', ha='left', bg=None)
    arrow(ax, [(K0[0], yC + 0.18), (K1[2], yC + 0.18)])
    label(ax, (K0[0] + K1[2]) / 2, yC + 0.62, '123 key')
    arrow(ax, [(K1[2], yC - 0.18), (K0[0], yC - 0.18)])
    label(ax, (K0[0] + K1[2]) / 2, yC - 0.62, 'ABC key')
    arrow(ax, [(K0[2], yC + 0.18), (K2[0], yC + 0.18)])
    label(ax, (K0[2] + K2[0]) / 2, yC + 0.62, 'Hindi key')
    arrow(ax, [(K2[0], yC - 0.18), (K0[2], yC - 0.18)])
    label(ax, (K0[2] + K2[0]) / 2, yC - 0.62, 'ABC key')
    arrow(ax, [(K2[2], yC + 0.18), (K3[0], yC + 0.18)])
    label(ax, (K2[2] + K3[0]) / 2, yC + 0.62, 'vowel-page key')
    arrow(ax, [(K3[0], yC - 0.18), (K2[2], yC - 0.18)])
    label(ax, (K2[2] + K3[0]) / 2, yC - 0.62, 'consonant key')
    arrow(ax, [(13.30, K3[1]), (13.30, 0.45), (4.60, 0.45), (4.60, K0[1])])
    label(ax, 9.05, 0.45, 'ABC key')
    save(fig, ax, 'states')


def main():
    print(f'schema: {len(TABLES)} tables, {len(FKS)} declared foreign keys; '
          f'API: {N_OPS} operations')
    fig_architecture()
    fig_deployment()
    fig_dataflow()
    fig_er()
    fig_seq_session()
    fig_seq_feedback()
    fig_states()


if __name__ == '__main__':
    main()
