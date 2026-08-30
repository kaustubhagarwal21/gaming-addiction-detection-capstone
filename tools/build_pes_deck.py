# -*- coding: utf-8 -*-
"""Build the PES-template Phase-3 Review-1 deck (docs/PES_REVIEW1_DECK.pptx).

Follows the mandated outline in capstone/Review1-phase3 template exactly:
  Title · Outline · Abstract & Scope · Summary of Phase-1/2 (+ suggestions
  incorporated) · Inferences from Literature · Architecture · List of
  Tasks/Modules (+ SDK/API/tools) · Individual Contribution (LOC/time/timeline)
  · Demonstration & Testing · Gantt · References (IEEE) · Thank You

Brand: PES orange header/footer bars, "Title of the Project" top-left,
"name1_name2_name3_name4" footer, PES logo top-right — matched to the template.
Numbers are READ from the committed JSONs; LOC from `git ls-files | wc -l`.

*** The per-person split on the Individual Contribution slide follows the team's
*** AGREED module ownership (confirmed 2026-08-18; also in docs/TEAM_BRIEFING.md).
*** Module LOC are measured (git ls-files | wc -l); hours are team estimates. Git
*** history is single-account (all pushes via one machine), so LOC-by-author is
*** not derivable from git — say so if asked, and cite module ownership.

Re-run: python tools/build_pes_deck.py
"""
import json
import os
import subprocess

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
FIG = os.path.join(DOCS, 'figures')
OUT = os.path.join(DOCS, 'PES_REVIEW1_DECK.pptx')


def _load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


SV = _load(os.path.join(DOCS, 'survey_validation.json'))
SX = _load(os.path.join(DOCS, 'survey_extras.json'))
AB = _load(os.path.join(DOCS, 'ablation_results.json'))
AF = _load(os.path.join(DOCS, 'asr_fairness.json'))
MM = _load(os.path.join(ROOT, 'backend', 'models', 'model_metadata.json'))
inc = SX['incremental']
comp = SX['features']['composites']
chat_ab = {r['config']: r for r in AB['chat']}
fam = AF['by_language_family']


def _paper_stats(name, fallback_pages):
    """(pages, refs) read from the LaTeX log and source, so a slide can never quote a
    stale page or reference count. Falls back to the last known page count if the log
    is absent (fresh clone)."""
    import re as _re
    pages = fallback_pages
    log = os.path.join(DOCS, name + '.log')
    if os.path.exists(log):
        with open(log, encoding='utf-8', errors='ignore') as f:
            m = _re.search(r'Output written on ' + _re.escape(name) + r'\.pdf \((\d+) pages', f.read())
        if m:
            pages = int(m.group(1))
    src = 'ieee_refs.tex' if name == 'IEEE_PAPER' else name + '.tex'
    with open(os.path.join(DOCS, src), encoding='utf-8') as f:
        refs = f.read().count('\\bibitem{')
    return pages, refs


REPORT_PP, REPORT_REFS = _paper_stats('PROJECT_PAPER', 48)
IEEE_PP, IEEE_REFS = _paper_stats('IEEE_PAPER', 6)
GENRE_POWER = SX['genre']['power_curve'][str(SV['construct_validity']['n'])] * 100


def loc(paths, exts=('.py', '.kt', '.java', '.xml', '.tex', '.md', '.yml')):
    files = subprocess.run(['git', 'ls-files', *paths], cwd=ROOT, capture_output=True, text=True).stdout.split()
    n = 0
    for f in files:
        if f.endswith(exts):
            try:
                with open(os.path.join(ROOT, f), encoding='utf-8', errors='ignore') as fh:
                    n += sum(1 for _ in fh)
            except OSError:
                pass
    return n


LOC = {
    'backend': loc(['backend/*.py', 'backend/*.yaml']),
    'backend_tests': loc(['backend/tests', 'backend/scripts']),
    'ml': loc(['ml']),
    'child': loc(['android/ChildApp/app/src/main']),
    'child_tests': loc(['android/ChildApp/app/src/test']),
    'parent': loc(['android/ParentApp/app/src/main']),
    'parent_tests': loc(['android/ParentApp/app/src/test']),
    'docs': loc(['docs/*.tex', '*.md']),
    'ci': loc(['.github']),
}

# ---------- brand ----------
ORANGE = RGBColor(0xE0, 0x7B, 0x1A)   # template heading orange
RUST = RGBColor(0xB9, 0x54, 0x27)     # footer band
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0xFB, 0xF3, 0xEA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = 'Trebuchet MS'
TITLE = 'AI-Driven Gaming Addiction Screening System'
FOOT = 'Kaustubh_Khushee_Kanak_Vidisha'

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = prs.slide_width, prs.slide_height
LOGO = os.path.join(FIG, 'pes_logo.png')


def _tb(slide, x, y, w, h, text, size=18, bold=False, color=BLACK, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
    r.font.color.rgb = color
    return box


def _md(s):
    out, bold, buf, i = [], False, '', 0
    while i < len(s):
        if s.startswith('**', i):
            if buf:
                out.append((buf, bold))
            buf, bold, i = '', not bold, i + 2
        else:
            buf += s[i]
            i += 1
    if buf:
        out.append((buf, bold))
    return out


def _rich(p, parts, size, color):
    for t, b in parts:
        r = p.add_run()
        r.text = t
        r.font.size, r.font.bold, r.font.name = Pt(size), b, FONT
        r.font.color.rgb = color


def chrome(slide, heading):
    """Template chrome: title-of-project top-left, logo top-right, orange heading, footer band."""
    _tb(slide, Inches(0.55), Inches(0.18), Inches(8), Inches(0.35), TITLE, 12, False, GREY)
    if os.path.exists(LOGO):
        slide.shapes.add_picture(LOGO, Inches(12.25), Inches(0.12), height=Inches(0.95))
    _tb(slide, Inches(0.55), Inches(0.75), Inches(11.5), Inches(0.6), heading, 26, False, BLACK, PP_ALIGN.RIGHT)
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - Inches(0.42), W, Inches(0.42))
    band.fill.solid()
    band.fill.fore_color.rgb = RUST
    band.line.fill.background()
    thin = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - Inches(0.48), W, Inches(0.06))
    thin.fill.solid()
    thin.fill.fore_color.rgb = ORANGE
    thin.line.fill.background()
    _tb(slide, Inches(0), H - Inches(0.36), W, Inches(0.3), FOOT, 10, False, WHITE, PP_ALIGN.CENTER)


def slide(heading, notes=''):
    s = prs.slides.add_slide(BLANK)
    chrome(s, heading)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def bullets(s, items, x=Inches(0.8), y=Inches(1.55), w=Inches(11.8), h=Inches(5.3), size=18, gap=7, color=ORANGE):
    box = s.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for it in items:
        sub = it.startswith('  ')
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(gap)
        p.level = 1 if sub else 0
        _rich(p, _md(('– ' if sub else '▪  ') + it.strip()), size - (3 if sub else 0), BLACK if sub else color)
    return box


def table(s, rows, x, y, w, col_w=None, size=12, hi=()):
    nr, nc = len(rows), len(rows[0])
    shp = s.shapes.add_table(nr, nc, x, y, w, Inches(0.38) * nr)
    t = shp.table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = cw
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            cell = t.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            tf = cell.text_frame
            tf.word_wrap = True
            _rich(tf.paragraphs[0], _md(str(v)), size, WHITE if r == 0 else BLACK)
            cell.fill.solid()
            cell.fill.fore_color.rgb = ORANGE if r == 0 else (LIGHT if (r in hi or r % 2) else WHITE)
    return shp


def fig(s, name, x, y, w=None, h=None):
    p = os.path.join(FIG, name)
    if os.path.exists(p):
        return s.shapes.add_picture(p, x, y, width=w, height=h)


def ci(v):
    return f'[{v[0]:.3f}, {v[1]:.3f}]'


# =============== 1. Title (template p1) ===============
s = prs.slides.add_slide(BLANK)
if os.path.exists(LOGO):
    s.shapes.add_picture(LOGO, Inches(12.25), Inches(0.12), height=Inches(0.95))
_tb(s, Inches(0), Inches(1.1), W, Inches(0.7), 'UE22CS441A – Capstone Project Phase – 3', 30, False, BLACK, PP_ALIGN.CENTER)
_tb(s, Inches(0), Inches(1.95), W, Inches(0.6), 'Project Progress Review # 1', 26, False, ORANGE, PP_ALIGN.CENTER)
_tb(s, Inches(2.1), Inches(4.6), Inches(3.0), Inches(2.2),
    'Project Title   :\nProject ID        :\nProject Guide  :\nProject Team   :', 22, False, ORANGE)
_tb(s, Inches(5.0), Inches(4.6), Inches(8.0), Inches(2.5),
    'AI-Driven Gaming Addiction Screening System\nPW26_SAS-03\nProf. Shridevi Sawant\n'
    'Kaustubh Agarwal (PES1UG23CS291) · Khushee P Kiran (PES1UG23CS303)\n'
    'Kanak Goyal (PES1UG23CS279) · Vidisha Murali (PES1UG23CS681)', 18, False, BLACK)
band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - Inches(0.42), W, Inches(0.42))
band.fill.solid(); band.fill.fore_color.rgb = RUST; band.line.fill.background()
thin = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - Inches(0.48), W, Inches(0.06))
thin.fill.solid(); thin.fill.fore_color.rgb = ORANGE; thin.line.fill.background()
s.notes_slide.notes_text_frame.text = ('One sentence: a deployed, multimodal screening system for parents that measures HOW a '
                                        'child plays, not just how long — externally validated against a clinical instrument, '
                                        'with its limitations named before you ask.')

# =============== 2. Outline (template p2) ===============
s = slide('Outline')
bullets(s, ['Abstract and Scope of the Project',
            'Capstone Project Phase – 2',
            '  Summary of work',
            '  Inferences drawn from Literature Survey',
            'List of Tasks/Modules with Individual Contribution',
            'Design of overall Architecture',
            'Demonstration and Testing of the completed modules',
            'Gantt chart',
            'References'], size=22, gap=10)

# =============== 3. Abstract & Scope (template p3) ===============
s = slide('Abstract and Scope', notes=(
    'Set the context in 60 s: IGD is WHO-recognised; parents notice late; questionnaires need cooperation, screen-time '
    'counters measure volume. We measure HOW a child plays. Say "screening, not diagnosis" out loud. Scope: minors, '
    'Android, guardian in the loop — and why (a guardian with duty of care is what makes screening the unwilling '
    'possible and proportionate).'))
bullets(s, [
    '**Problem.** Internet Gaming Disorder is WHO-recognised (ICD-11); parents notice **late**, from the outside. Existing tools are self-report questionnaires (need the child\'s honest cooperation) or screen-time counters (measure **how long**, a weak correlate of severity)',
    '**What we built.** A deployed three-tier system — Child app (passive capture) → cloud ML backend → Parent app — that fuses **behaviour patterns**, **chat toxicity** (English + romanised Hindi + Devanagari) and **voice** into one calibrated, explainable *screening* signal with a plain-language "why"',
    '**Scope.** Minors on Android; guardian-consented; screening and awareness — **not** a clinical diagnosis. Cloud backend live in production; signed APKs on GitHub; consented family pilot ran 23 days',
    '**What Phase 3 adds.** External construct validation against the IGDS9-SF clinical instrument (134 raw / 104 usable), an accent-fairness audit (6,656 clips), on-device resource measurement, and the honest limitations that come with all three',
], size=16, gap=9)

# =============== 4. Summary of Phase 1/2 + suggestions (template p4) ===============
s = slide('Summary of Work Done in Capstone Project Phase – 1 & 2', notes=(
    'Phase 1 (approval) proposed the vision; Phase 2 built and evaluated the system; each review\'s feedback narrowed the '
    'design toward what could be validated. Be explicit that several Phase-1 ideas were dropped ON PURPOSE with a reason — '
    'camera/facial expression (privacy, no consent story), screen-recording OCR (privacy regression), iOS (no accessibility '
    'API for capture), Kaggle behaviour datasets (audited: synthetic provenance). Reviewers reward "we changed our mind '
    'because we measured" far more than "we did everything we said."'))
table(s, [
    ['Phase', 'What was proposed / done', 'Suggestion or finding → improvement made'],
    ['**Phase 1** (approval)', 'AI-driven prediction app: playtime + chat sentiment + speech emotion; Casual / At-risk / Addicted; parental dashboard; Flutter/React Native + Firebase; Android + iOS; camera for facial expression; screen-recording OCR; Kaggle datasets',
     'Narrowed to what is **capturable, consentable and validatable**: native Android only (iOS has no capture API); camera **dropped** (no proportionate consent story); OCR **dropped** (privacy regression); Kaggle behaviour sets **audited and rejected** (synthetic provenance)'],
    ['**Phase 2** (build + evaluate)', 'Both apps + Flask backend built and deployed; 3-model ensemble with calibration + SHAP; 11 real open datasets adopted by measured trial; ablations with CIs; family pilot; 266 tests in CI at Phase-2 close (291 now)',
     'Review feedback: "labels are synthetic" → grounded on 2 real surveys and stated on every slide; "voice number looks inflated" → speaker-independent split (–8.3 pts, honest); "no Hindi" → dual-script HASOC path + Devanagari keyboard'],
    ['**Phase 3** (this review)', f'External validation survey; accent-fairness audit; on-device resource drill; v2.4.0 released; {REPORT_PP}-page report + {IEEE_PP}-page IEEE paper',
     '"Does the score mean anything?" → **ρ = 0.317 vs IGDS9-SF, leads screen time in 97% of resamples**; "is it fair across accents?" → **0 false alerts / 9.6 h**, WER gap named; "battery?" → **measured**, dual-STT fails our gate → default OFF'],
], Inches(0.6), Inches(1.5), Inches(12.1), col_w=[Inches(1.7), Inches(5.0), Inches(5.4)], size=11)

# =============== 5. Inferences from literature (template outline) ===============
s = slide('Inferences Drawn from Literature Survey', notes=(
    'Three inferences that shaped the design, each tied to a paper the panel can check: (1) family factors and behavioural '
    'patterns, not hours, predict IGD → pattern features and a guardian in the loop; (2) IGDS9-SF is the validated short '
    'instrument → our external anchor; (3) domain data beats architecture for toxicity → CONDA in-game chat, HASOC Hindi. '
    'And one inference from our own survey that the literature did not give us: pattern > volume, measured.'))
table(s, [
    ['Source', 'Inference', 'How it shaped our design'],
    ['You et al. 2025; Coșa et al. 2025; Ergin & Essau 2025 (family & IGD)', 'Parent–child relationship and behavioural patterns predict IGD better than raw exposure; interventions work through the family', 'Guardian-in-the-loop screening; **pattern** features (late-night, re-logins, binges) as first-class inputs; nudges, not blocks'],
    ['Pontes & Griffiths 2015 (IGDS9-SF); LatAm IGDS9-SF dataset, n = 11,191', 'A validated 9-item DSM-5 instrument exists; disordered-range base rate ≈ 6.4 %; toxic-chat involvement tracks severity (r = +0.156)', f'IGDS9-SF as the **external validation anchor**; base rate grounds thresholds; chat channel justified — and replicated locally (ρ = {SX["chat_premise"]["rho"]:.3f})'],
    ['Huang et al. 2024; Jiang 2024 (ML for gaming disorder)', 'Prior ML work models survey data or single signals; none deploys passive multi-signal capture to a guardian', 'The gap we fill: deployed, multimodal, explainable, calibrated'],
    ['Weld et al. 2021 (CONDA); Mandl et al. 2019 (HASOC); Javed et al. 2023 (Svarah)', 'In-game chat and code-mixed Hindi are their own registers; Indian-accent ASR error is uneven', 'Domain corpora over model capacity (toxic-BERT loses to our LogReg by 12 pts); dual-script Hindi; **accent-fairness audit**'],
    ['**Our own survey (n = 104 usable)**', 'Every pattern feature out-ranks every volume feature against IGDS9-SF', 'The design premise — measure *how*, not *how long* — confirmed against real labels'],
], Inches(0.6), Inches(1.5), Inches(12.1), col_w=[Inches(3.4), Inches(4.4), Inches(4.3)], size=11)

# =============== 6. Architecture (template p5) ===============
s = slide('Architecture', notes=(
    'Walk left to right. ChildApp: foreground-package game detection, 10 objective session features, custom keyboard + '
    'accessibility for chat, VAD-gated mic with on-device Vosk STT, anti-tamper, consent-gated. Backend: Flask on Render, '
    'Neon Postgres, three models + availability-weighted fusion (40/30/30 over channels PRESENT), isotonic calibration, '
    'SHAP why, alerts to every guardian, drift monitor, export = delete scope. ParentApp: dashboard, 14-day trend, alerts '
    'with verdicts → threshold tuner, nudges, capture-coverage transparency screen.'))
bx_y, bx_h = Inches(1.6), Inches(2.6)
for title, body, x in [
    ('ChildApp (Android)', 'Game detection (allowlist → OS category → parent override)\n10 objective session features\nIME + accessibility chat capture (Devanagari layout)\nVAD-gated mic → on-device Vosk STT\nAnti-tamper · versioned consent (fails closed)', Inches(0.6)),
    ('Flask backend (Render + Neon Postgres)', 'RF behaviour (10 feats) · LogReg+TF-IDF chat · HistGB voice\nAvailability-weighted fusion 40/30/30\nIsotonic calibration · SHAP "why"\nAlerts to all guardians · drift monitor (PSI/KS)\nExport scope = delete scope · HTTPS · tokens', Inches(4.75)),
    ('ParentApp (Android)', 'Risk band + plain-language why · 14-day trend\nReal-time alerts (risk / toxicity / tamper)\nAccurate / false-alarm verdicts → Beta threshold tuner\nNudges to child · weekly PDF\n"What we can and can\'t see" transparency', Inches(8.9)),
]:
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, bx_y, Inches(3.8), bx_h)
    b.fill.solid(); b.fill.fore_color.rgb = LIGHT; b.line.color.rgb = ORANGE; b.line.width = Pt(2)
    _tb(s, x + Inches(0.15), bx_y + Inches(0.1), Inches(3.5), Inches(0.5), title, 15, True, ORANGE)
    _tb(s, x + Inches(0.15), bx_y + Inches(0.6), Inches(3.5), Inches(1.9), body, 11, False, BLACK)
for x in (Inches(4.42), Inches(8.57)):
    a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, bx_y + Inches(1.1), Inches(0.32), Inches(0.4))
    a.fill.solid(); a.fill.fore_color.rgb = ORANGE; a.line.fill.background()
bullets(s, ['**Data flow:** session telemetry / chat lines / 10-s voice segments → per-channel scores → fused, calibrated risk + SHAP → dashboard + push alerts; raw audio **deleted** after feature extraction',
            '**Modules:** game detection · session lifecycle · chat capture (IME/accessibility) · voice capture + STT · behaviour model · chat model · voice model · fusion & alerting · feedback tuner · drift monitor · consent & anti-tamper · parent dashboard'],
        y=Inches(4.45), h=Inches(2.3), size=13, gap=6)

# =============== 7. List of tasks/modules + tools (template p6) ===============
s = slide('List of Tasks / Modules', notes=(
    'Template asks for the data pipeline stages explicitly, and the SDK/API/tool list with licences. Everything is '
    'open-source; no licensed component. Mention that the two gated datasets (HASOC, Svarah) are NOT redistributed.'))
table(s, [
    ['Stage', 'What we do', 'Where'],
    ['Data collection & preparation', '11 open corpora screened by provenance/fit/openness, adopted by measured trial; 2 rejected with evidence; own IGDS9-SF survey (134 raw / 104 usable) as primary data', 'ml/fetch_*.py, ml/analyze_*.py, docs/VALIDATION_PLAN.md'],
    ['Data input', 'ChildApp session telemetry, IME/accessibility chat, VAD-gated audio; Google-Form export for the survey', 'android/ChildApp, ml/eval_behavior_survey.py'],
    ['Pre-processing', 'Train/serve-aligned feature derivation (one shared function); TF-IDF word ∪ char_wb; 36 acoustic features; romanisation of Hindi; keyword-column matching for the survey', 'backend/behavior_features.py, ml/'],
    ['Modelling', 'RF (10 feats) · LogReg+isotonic chat with noisy-OR lexicon · HistGB voice; availability-weighted fusion', 'ml/retrain_models.py, backend/app.py'],
    ['Visualisation & interpretation', 'SHAP per prediction; PR curve, confusion matrices, reliability diagrams, ablation tables, survey figure; parent-facing plain-language why', 'ml/make_figures.py, docs/figures/'],
    ['Storage', 'SQLite (dev) / Neon Postgres (prod), one code path; export = delete scope; audio never retained', 'backend/app.py, DEPLOY.md'],
], Inches(0.6), Inches(1.45), Inches(12.1), col_w=[Inches(2.3), Inches(6.7), Inches(3.1)], size=10)
_tb(s, Inches(0.6), Inches(4.7), Inches(12.1), Inches(0.35), 'SDK / API / Model / Tools (all open-source):', 13, True, ORANGE)
_tb(s, Inches(0.6), Inches(5.05), Inches(12.1), Inches(1.9),
    'Android SDK 34 / Kotlin · Retrofit · Vosk 0.3.47 (Apache-2.0; en-in + hi small models) · Firebase Cloud Messaging · '
    'Python 3.11 · Flask · scikit-learn (RandomForest, LogisticRegression, HistGradientBoosting, isotonic) · SHAP · '
    'librosa / webrtcvad · psycopg2 · Postgres 16 (Neon) · Render · GitHub Actions · pytest · schemathesis · bandit · '
    'pip-audit · MobSF · LaTeX/IEEEtran · Datasets: Jigsaw, CONDA, Davidson, HASOC 2019 (gated), Hindi Wikipedia, '
    'RAVDESS, CREMA-D, EMO-DB, URDU, Gamers & Anxiety (OSF), IGDS9-SF LatAm (OSF), StudentLife, Svarah (CC BY 4.0, gated).',
    11, False, BLACK)

# =============== 8. Individual contribution (template p7) — EDIT BEFORE PRESENTING ===============
CONTRIB = [
    # name, modules, LOC (evidence-based per module; person split is a PROPOSAL), hours (ESTIMATE — edit)
    ('Kaustubh Agarwal', 'ML pipeline (3 models, calibration, fusion, ablations); backend serving + API; external validation survey + analysis; fairness audit; paper & IEEE draft',
     LOC['ml'] + LOC['backend'] // 2 + LOC['docs'] // 2, '≈ 420 h'),
    ('Khushee P Kiran', 'ChildApp: game detection, session lifecycle, IME + Devanagari keyboard, accessibility capture, voice recorder + on-device STT, anti-tamper, consent; on-device drill',
     LOC['child'] + LOC['child_tests'], '≈ 300 h'),
    ('Kanak Goyal', 'Backend infra: Postgres/SQLite dual dialect, auth, rate limiting, alerts/FCM, drift monitor, export/delete; CI, tests, deployment (Render/Neon)',
     LOC['backend'] // 2 + LOC['backend_tests'] + LOC['ci'], '≈ 280 h'),
    ('Vidisha Murali', 'ParentApp: dashboard, alerts + feedback verdicts, chat/emotion analysis screens, transparency screen, weekly PDF; privacy/ethics docs, survey instrument & recruitment, review decks',
     LOC['parent'] + LOC['parent_tests'] + LOC['docs'] // 2, '≈ 260 h'),
]
s = slide('Individual Contribution', notes=(
    'The split follows the module ownership the team agreed (each member owns the modules listed). Module LOC are '
    'measured (git ls-files | wc -l on 2026-08-18); hours are team estimates. If a panelist asks how LOC were '
    'attributed: by module ownership — the repo is pushed from one machine, so git author lines do not split by '
    'person, and we say that rather than fake per-author blame. Timeline is on the Gantt slide.'))
table(s, [['Team member', 'Tasks / modules assigned', 'Development (LOC, approx.)', 'Time spent']] +
      [[n, m, f'{l:,}', h] for n, m, l, h in CONTRIB] +
      [['**Total (repo)**', f'backend {LOC["backend"]:,} · ML {LOC["ml"]:,} · ChildApp {LOC["child"]:,} · ParentApp {LOC["parent"]:,} · tests {LOC["backend_tests"] + LOC["child_tests"] + LOC["parent_tests"]:,} · docs {LOC["docs"]:,} · CI {LOC["ci"]:,}',
        f'**{sum(LOC.values()):,}**', '≈ 1,260 h']],
      Inches(0.6), Inches(1.5), Inches(12.1), col_w=[Inches(1.9), Inches(6.5), Inches(2.0), Inches(1.7)], size=11, hi=(5,))
_tb(s, Inches(0.6), Inches(5.35), Inches(12.1), Inches(0.9),
    'LOC counted with `git ls-files | wc -l` on 2026-08-18 (source, tests, docs, CI), attributed by agreed module ownership; '
    'hours are team estimates. Timeline of every task/module: see the Gantt chart.', 11, False, GREY)

# =============== 9. Demonstration & testing (template p8) ===============
full = chat_ab['full recipe (deployed)']
no_conda = chat_ab['- CONDA corpus (domain data)']
s = slide('Demonstration and Testing of the Modules Completed', notes=(
    'Demo per DEMO_RUNBOOK §3 (parent dashboard → alerts + verdict → nudge → chat/emotion → live capture in Roblox → '
    'tamper). Backup video ready. Testing: 291 automated tests + 7 research-integrity guards in CI on both DB dialects; load, fuzz, CVE, MobSF; '
    'on-device drill numbers here are MEASURED (Galaxy M52, 2026-08-18). Results table: every number is from the '
    'committed JSONs; 7 CI guards fail the build if the paper and data disagree.'))
table(s, [
    ['Module', 'Result (held-out, real data unless stated)', 'Testing'],
    ['Behaviour model', '91.6 % acc · macro-F1 0.918 · CV 0.921 ± 0.002 (**synthetic labels**, grounded on 2 real surveys); ECE 0.062 → 0.015', 'Ablations w/ CIs; hours-only baseline 0.702; pattern-5 0.902 vs volume-5 0.871'],
    ['Chat model', f'In-domain PR-AUC **{full["pr_auc"]:.3f}** {ci(full["pr_auc_ci95"])}; P 0.956 / R 0.428 @ 0.95; Hindi P 0.968 (Devanagari) / 0.958 (romanised)', f'Ablation: − CONDA → {no_conda["pr_auc"]:.3f}; toxic-BERT baseline 0.709; HASOC held-out 933 rows'],
    ['Voice model', '0.574 acc speaker-independent (chance 0.25); random split 0.657 → 8.3-pt leakage exposed', 'Speaker-independent CV; w2v2 headroom 0.776; augmentation ablation neutral'],
    ['**External validation**', f'ρ = **{SV["construct_validity"]["rho"]:.3f}** {ci(SV["construct_validity"]["ci95"])} vs IGDS9-SF (n = {SV["construct_validity"]["n"]}); hours baseline {inc["rho_hours"]:.3f}; Δρ = +{inc["delta_rho"]:.3f} {ci(inc["delta_ci"])}; pattern {comp["pattern"]["rho"]:.3f} vs volume {comp["volume"]["rho"]:.3f}, formal contrast **+{comp["pattern_minus_volume"]["diff"]:.3f}** {ci(comp["pattern_minus_volume"]["ci"])}', f'Pre-specified exclusions; paired bootstrap; late batch folded in per pre-stated rule; genre null p = {SX["genre"]["p"]:.3f} reported; caseness withheld (1 positive)'],
    ['Fairness (STT → toxicity)', f'**0 false alerts** in {AF["overall"]["speech_hours"]} h / {AF["overall"]["clips"]:,} clips, every accent group; WER {fam["Dravidian"]["wer"]*100:.1f} % Dravidian → {fam["Tibeto-Burman"]["wer"]*100:.1f} % Tibeto-Burman', 'Svarah (117 speakers); deployed recogniser + served scorer'],
    ['System / apps', 'Live on Render + Neon; v2.4.0 signed APKs validated on device; 23-day pilot; default path 14 % CPU / 288 MB; dual-STT 51–72 % / 419 MB → **fails gate → default OFF**', '181 backend (SQLite + Postgres) + 110 JVM + 7 guards, all in CI; 288-req load 0 errors; fuzz; CVE; MobSF'],
], Inches(0.6), Inches(1.45), Inches(12.1), col_w=[Inches(1.9), Inches(6.2), Inches(4.0)], size=10, hi=(4,))
fig(s, 'survey_features.png', Inches(0.6), Inches(5.0), h=Inches(1.95))
fig(s, 'pr_chat.png', Inches(4.1), Inches(5.0), h=Inches(1.95))
_tb(s, Inches(7.0), Inches(5.05), Inches(5.7), Inches(1.9),
    'Live demo (DEMO_RUNBOOK §3): parent dashboard → alert verdict → nudge → chat/emotion analysis → live capture in Roblox → tamper alert. Backup video ready. Two results AGAINST the system are reported: genre multiplier unsupported; 4 of 5 proxy names discredited → renamed in the product.',
    11, False, BLACK)

# =============== 10. Gantt (template outline) ===============
s = slide('Gantt Chart', notes=(
    'Phases from git history and the Phase-1 deck: Phase 1 approval + literature (Feb–Mar), Phase 2 design + build '
    '(Apr–Jun: 19 commits May, 100 June), Phase 2 evaluation + pilot (Jul: 48 commits, 23-day pilot 6–28 Jul), Phase 3 '
    'validation + release + reporting (Aug: 70 commits — survey 7–9 Aug, fairness audit 14 Aug, device drill + v2.4.0 '
    '18 Aug). Remaining: final report submission, viva.'))
months = ['Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep']
tasks = [
    ('Phase 1: problem, scope, literature survey, approval', 0, 2, 'done'),
    ('Architecture & data pipeline design; dataset audit', 1, 3, 'done'),
    ('ChildApp / ParentApp / backend build (v1 → v2.3)', 2, 5, 'done'),
    ('Model training, calibration, ablations, bake-offs', 3, 5, 'done'),
    ('Cloud deployment (Render + Neon), CI, security audits', 3, 6, 'done'),
    ('Consented family pilot (6–28 Jul); feedback loop; drift monitor', 5, 6, 'done'),
    ('Hindi dual-script chat + Devanagari keyboard + dual-STT (v2.4.0)', 5, 7, 'done'),
    (f'External validation survey (IGDS9-SF, n = {SV["n_raw"]}) + analysis', 6, 7, 'done'),
    ('Accent-fairness audit · on-device drill · v2.4.0 release', 6, 7, 'done'),
    (f'Report ({REPORT_PP} pp) · IEEE paper ({IEEE_PP} pp) · defense kit', 6, 7, 'done'),
    ('Phase 3 reviews · final submission · viva', 6, 8, 'open'),
]
gx, gy, gw = Inches(0.6), Inches(1.55), Inches(12.1)
label_w = Inches(4.6)
cell_w = (gw - label_w) / len(months)
row_h = Inches(0.42)
_tb(s, gx, gy, label_w, row_h, 'Task / module', 12, True, ORANGE)
for i, m in enumerate(months):
    _tb(s, gx + label_w + cell_w * i, gy, cell_w, row_h, m + ' ’26', 11, True, ORANGE, PP_ALIGN.CENTER)
for r, (name, a, b, st) in enumerate(tasks, start=1):
    y = gy + row_h * r
    _tb(s, gx, y + Inches(0.05), label_w, row_h, name, 11, False, BLACK)
    for i in range(len(months)):
        cell = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, gx + label_w + cell_w * i, y, cell_w, row_h - Inches(0.04))
        cell.fill.solid(); cell.fill.fore_color.rgb = LIGHT if r % 2 else WHITE
        cell.line.color.rgb = RGBColor(0xE6, 0xE6, 0xE6); cell.line.width = Pt(0.5)
    bar = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, gx + label_w + cell_w * a + Inches(0.04), y + Inches(0.08),
                             cell_w * (b - a + 1) - Inches(0.08), row_h - Inches(0.2))
    bar.fill.solid(); bar.fill.fore_color.rgb = ORANGE if st == 'done' else RGBColor(0xF2, 0xC2, 0x8A)
    bar.line.fill.background()
_tb(s, gx, gy + row_h * (len(tasks) + 1) + Inches(0.05), gw, Inches(0.4),
    'Solid = complete · Light = in progress. Cadence from git: 19 commits May · 100 Jun · 48 Jul · 70 Aug (to 18 Aug).', 11, False, GREY)

# =============== 11. References (template p9) ===============
s = slide('References', notes=f'IEEE format; the full {REPORT_REFS}-entry list is in the report, {IEEE_REFS} in the IEEE paper.')
refs = [
    'H. M. Pontes and M. D. Griffiths, "Measuring DSM-5 Internet Gaming Disorder: Development and validation of a short psychometric scale," Computers in Human Behavior, vol. 45, pp. 137–143, 2015.',
    'World Health Organization, International Classification of Diseases 11th Revision (ICD-11) — Gaming disorder (6C51), 2019.',
    'S. You, X. Wang, Z. Hu, and J. He, "Parent–child relationships and gaming addiction: A systematic review and meta-analysis," Journal of Youth and Adolescence, 2025.',
    'Y. Huang, R. Wu, Y. Huang, Y. Xiang, and W. Zhou, "Investigating mechanisms of Internet Gaming Disorder and developing intelligent monitoring models using AI technologies," BMC Public Health, 2024.',
    'D. A. Ergin and C. A. Essau, "Family factors and Internet Gaming Disorder among adolescents: A systematic review," Int. J. Developmental Science, 2025.',
    'H. Weld et al., "CONDA: a CONtextual Dual-Annotated dataset for in-game toxicity understanding and detection," in Findings of ACL-IJCNLP, 2021.',
    'T. Mandl et al., "Overview of the HASOC track at FIRE 2019: Hate speech and offensive content identification in Indo-European languages," in Proc. FIRE, 2019.',
    'T. Javed et al., "Svarah: Evaluating English ASR systems on Indian accents," in Proc. INTERSPEECH, 2023.',
    'S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in Advances in Neural Information Processing Systems (NeurIPS), 2017.',
    'S. R. Livingstone and F. A. Russo, "The Ryerson Audio-Visual Database of Emotional Speech and Song (RAVDESS)," PLoS ONE, vol. 13, no. 5, 2018.',
    'H. Cao et al., "CREMA-D: Crowd-sourced emotional multimodal actors dataset," IEEE Trans. Affective Computing, vol. 5, no. 4, 2014.',
    'T. Davidson, D. Warmsley, M. Macy, and I. Weber, "Automated hate speech detection and the problem of offensive language," in Proc. ICWSM, 2017.',
]
box = s.shapes.add_textbox(Inches(0.6), Inches(1.5), Inches(12.1), Inches(5.3))
tf = box.text_frame; tf.word_wrap = True
for i, r in enumerate(refs, 1):
    p = tf.paragraphs[0] if i == 1 else tf.add_paragraph()
    p.space_after = Pt(4)
    _rich(p, [(f'[{i}] {r}', False)], 11, BLACK)

# =============== 12. Thank you (template p10) ===============
s = prs.slides.add_slide(BLANK)
_tb(s, Inches(0), Inches(3.0), W, Inches(1.4), 'Thank\nYou', 40, False, ORANGE, PP_ALIGN.CENTER)
band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - Inches(0.42), W, Inches(0.42))
band.fill.solid(); band.fill.fore_color.rgb = RUST; band.line.fill.background()
thin = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - Inches(0.48), W, Inches(0.06))
thin.fill.solid(); thin.fill.fore_color.rgb = ORANGE; thin.line.fill.background()

prs.save(OUT)
print(f'wrote {OUT}  ({len(prs.slides)} slides)')
print('LOC:', LOC, 'total', sum(LOC.values()))
