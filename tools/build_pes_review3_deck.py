# -*- coding: utf-8 -*-
"""Build the Phase-3 Review-3 deck ON THE DEPARTMENT'S TEMPLATE (docs/PES_REVIEW3_DECK.pptx).

Template: docs/templates/PES_Review3_template.pptx (13.333 x 7.5 in, theme "Retrospect").
  - slide 1 (title), slide 2 (Outline) and slide 16 (Thank You) are KEPT and filled in;
  - slides 3-15 (the department's instructions) are removed properly (sldIdLst entry
    and presentation relationship), and the slide parts are renumbered;
  - every content slide is added on the template's BLANK layout, which carries the rust
    footer band, and gets the template's own chrome deep-copied from template slide 4:
    grey project title top-left (Arial 12), PES logo top-right (same image part),
    red 24 pt Trebuchet heading right-aligned, orange rule (theme accent 1) and the
    footer placeholder (idx 11) carrying the team's names.
Under the rule each slide states its takeaway first (bold, right-aligned like the
heading), then the body: black on white with orange accents, as in the Review 2 deck.

Slide text: docs/review3/*.json (slide objects, sorted by "order"; drafted and judged
against the code and the committed data) and docs/review3/90_references.json
(auto-paginated at order 730). Every number is a {placeholder} filled by
tools/project_numbers.fill(), so the deck cannot drift from the data.

Fitting: text is measured with the real TrueType fonts (Trebuchet MS, Consolas) and each
block takes the largest size that fits above the footer band (body >= 14 pt,
tables and code >= 11 pt). A slide that cannot fit at the minimum is reported.

Usage:
  python tools/build_pes_review3_deck.py             # strict: unknown or pending keys raise
  python tools/build_pes_review3_deck.py --preview   # pending keys render as [pending]
Render with PowerPoint (Windows):
  & tools/render_pptx.ps1 -Pptx <absolute path to the deck> -OutDir <dir> -Width 1600
"""
import argparse
import copy
import glob
import io
import json
import math
import os
import re
import sys

from lxml import etree
from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
TPL = os.path.join(DOCS, 'templates', 'PES_Review3_template.pptx')
SRC = os.path.join(DOCS, 'review3')
OUT = os.path.join(DOCS, 'PES_REVIEW3_DECK.pptx')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_numbers as PN  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
ap.add_argument('--preview', action='store_true',
                help="render not-yet-available numbers as '[pending]' instead of failing")
ap.add_argument('--out', default=OUT, help='output .pptx (default: docs/PES_REVIEW3_DECK.pptx)')
ARGS = ap.parse_args()
PENDING = '[pending]' if ARGS.preview else None


def F(s):
    """Fill {placeholders}; strict unless --preview (unknown keys always raise)."""
    return PN.fill(s, pending=PENDING)


# ---------------------------------------------------------------- facts
TITLE = 'AI-Driven Gaming Addiction Screening System'
PROJECT_ID = 'PW26_SAS-03'
GUIDE = 'Prof. Shridevi Sawant'
TEAM = ['Kaustubh Agarwal (PES1UG23CS291)', 'Khushee P Kiran (PES1UG23CS303)',
        'Kanak Goyal (PES1UG23CS279)', 'Vidisha Murali (PES1UG23CS681)']
FOOT = 'Kaustubh_Khushee_Kanak_Vidisha'

# ---------------------------------------------------------------- brand (template theme)
ORANGE = RGBColor(0xE4, 0x83, 0x12)   # theme accent1: rule, template body text
RUST = RGBColor(0xBD, 0x58, 0x2C)     # theme accent2: footer band
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x5F, 0x5F, 0x5F)
DARK = RGBColor(0x5A, 0x2E, 0x0E)
LIGHT = RGBColor(0xFB, 0xF3, 0xEA)
CODEBG = RGBColor(0xF7, 0xF4, 0xEF)
PALE = RGBColor(0xEE, 0xC9, 0x9E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT, MONO = 'Trebuchet MS', 'Consolas'

# ---------------------------------------------------------------- geometry (inches)
SW = 13.333
X0, X1 = 0.6, 12.73          # body left / right edge
BODY_W = X1 - X0
HEAD_X = 0.6                 # heading box widened leftwards; right edge stays the template's
RULE_BOTTOM = 1.77           # template rule: (3.33, 1.73) 8.33 x 0.04
TAKE_Y, TAKE_R = 1.79, 11.70  # takeaway box top and right edge (text ends under the rule end)
REF_TOP = 1.97               # content top when a slide has no takeaway
BAND_TOP = 6.93              # layout's footer band (thin orange line, then rust band)
BOTTOM = 6.84                # nothing of ours goes below this
LH = 1.2                     # line pitch / font size used for measuring
INS, INS_V = 0.05, 0.03      # text-box insets
BUL = 0.3                    # bullet hanging indent
CM_LR, CM_TB = 0.07, 0.045   # table cell margins

WARN = []


def warn(msg):
    WARN.append(msg)


# ---------------------------------------------------------------- text measurement
_FONT_FILES = {
    (FONT, 0, 0): 'trebuc.ttf', (FONT, 1, 0): 'trebucbd.ttf',
    (FONT, 0, 1): 'trebucit.ttf', (FONT, 1, 1): 'trebucbi.ttf',
    (MONO, 0, 0): 'consola.ttf', (MONO, 1, 0): 'consolab.ttf',
    (MONO, 0, 1): 'consolai.ttf', (MONO, 1, 1): 'consolaz.ttf',
}
_FC = {}


def _pil(font, bold, italic):
    key = (font, int(bool(bold)), int(bool(italic)))
    if key not in _FC:
        fname = _FONT_FILES.get(key, 'arial.ttf')
        try:
            _FC[key] = ImageFont.truetype(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', fname), 200)
        except OSError:
            _FC[key] = None
    return _FC[key]


def text_w(t, size, bold=False, italic=False, font=FONT):
    """Width in inches of `t` set at `size` pt."""
    t = t.replace('\u200b', '')
    f = _pil(font, bold, italic)
    if f is None:   # no font file: conservative estimate
        return len(t) * size * (0.6 if font == MONO else 0.55) / 72
    return f.getlength(t) / 200 * size / 72


# a word plus its trailing space; a hyphen ends a token too, since PowerPoint may wrap after it
_TOK = re.compile(r'[^\s\u200b]+?(?:-(?=[A-Za-z])|[\s\u200b]+|$)')


def typo(s):
    """Display text only: a hyphen used as a minus sign ('[-0.002') becomes U+2212, which
    PowerPoint never separates from its number; ranges such as 'Feb-May' or '3-5' stay."""
    return re.sub(r'(?<![\w.)\]])-(?=\.?\d)', '\u2212', s)


WF = 1.025   # PowerPoint wraps a hair earlier than the fonts' nominal advances (seen in renders)


def n_lines(parts, size, width, font=FONT, italic=False):
    """Greedy word wrap of [(text, bold)] runs into `width` inches -> number of lines."""
    lines, cur = 1, 0.0
    for t, b in parts:
        lead = len(t) - len(t.lstrip(' '))
        if lead and cur > 0:     # the space that joins this run to the previous one
            cur += text_w(' ' * lead, size, b, italic, font) * WF
        for m in _TOK.finditer(t):
            tok = m.group(0)
            wb = text_w(tok.rstrip(), size, b, italic, font) * WF
            wf = text_w(tok, size, b, italic, font) * WF
            if cur > 0 and cur + wb > width:
                lines += 1
                cur = 0.0
            if wb > width:          # one over-long word: PowerPoint breaks it anywhere
                lines += int(wb // width)
                cur = wb % width + (wf - wb)
            else:
                cur += wf
    return lines


def prep(parts, size, width, font=FONT):
    """Let PowerPoint wrap identifiers wider than the column: zero-width space after _ / ."""
    def fix(m):
        w = m.group(0)
        if text_w(w, size, True, False, font) <= width:
            return w
        return re.sub(r'([_/.])(?=\w)', '\\1\u200b', w)
    return [(re.sub(r'\S+', fix, t), b) for t, b in parts]


def _md(s):
    """'**bold**' markup -> [(text, bold)]."""
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


def P(text, size, color=BLACK, bold=False, italic=False, font=FONT, align=None, after=0.0,
      bullet=False, label=None, hang=0.0):
    parts = _md(typo(text))
    if bold:
        parts = [(t, True) for t, _ in parts]
    return dict(parts=parts, size=size, color=color, italic=italic, font=font, align=align,
                after=after, bullet=bullet, label=label, hang=hang)


def _text_width(pd, width):
    return width - (BUL if pd['bullet'] else 0) - pd['hang']


def p_height(pd, width):
    """Height (in) of one paragraph laid out in a text area `width` inches wide."""
    w = _text_width(pd, width)
    parts = prep(pd['parts'], pd['size'], w, pd['font'])
    return n_lines(parts, pd['size'], w, pd['font'], pd['italic']) * pd['size'] * LH / 72 + pd['after'] / 72


def ps_height(ps, box_w):
    """Height (in) of a text box `box_w` wide holding paragraphs `ps` (insets included)."""
    return sum(p_height(pd, box_w - 2 * INS) for pd in ps) + 2 * INS_V


# ---------------------------------------------------------------- drawing helpers
def _bullet(p, color=ORANGE):
    pPr = p._p.get_or_add_pPr()
    pPr.set('marL', str(Inches(BUL)))
    pPr.set('indent', str(-Inches(BUL)))
    for el in pPr.findall(qn('a:buNone')):
        pPr.remove(el)
    clr = etree.SubElement(pPr, qn('a:buClr'))
    etree.SubElement(clr, qn('a:srgbClr'), val=str(color))
    etree.SubElement(pPr, qn('a:buSzPct'), val='100000')
    etree.SubElement(pPr, qn('a:buFont'), typeface='Arial')
    etree.SubElement(pPr, qn('a:buChar'), char='\u25aa')


def _hang(p, hang):
    pPr = p._p.get_or_add_pPr()
    pPr.set('marL', str(Inches(hang)))
    pPr.set('indent', str(-Inches(hang)))
    tabs = etree.SubElement(pPr, qn('a:tabLst'))
    etree.SubElement(tabs, qn('a:tab'), pos=str(Inches(hang)), algn='l')


def _run(p, text, size, bold=False, italic=False, color=BLACK, font=FONT):
    r = p.add_run()
    r.text = text
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = color
    return r


def _fill_para(p, pd, width):
    if pd['align'] is not None:
        p.alignment = pd['align']
    if pd['after']:
        p.space_after = Pt(pd['after'])
    if pd['bullet']:
        _bullet(p)
    if pd['hang']:
        _hang(p, pd['hang'])
    if pd['label'] is not None:
        _run(p, pd['label'] + '\t', pd['size'], False, pd['italic'], pd['color'], pd['font'])
    for t, b in prep(pd['parts'], pd['size'], _text_width(pd, width), pd['font']):
        _run(p, t, pd['size'], b, pd['italic'], pd['color'], pd['font'])


def add_text(s, x, y, w, h, ps, anchor=MSO_ANCHOR.TOP):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = Inches(INS)
    tf.margin_top = tf.margin_bottom = Inches(INS_V)
    tf.vertical_anchor = anchor
    for i, pd in enumerate(ps):
        _fill_para(tf.paragraphs[0] if i == 0 else tf.add_paragraph(), pd, w - 2 * INS)
    return box


def add_box(s, x, y, w, h, fill=LIGHT, line=ORANGE, lw=1.5, shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.05):
    b = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        b.adjustments[0] = adj
    if fill is None:
        b.fill.background()
    else:
        b.fill.solid()
        b.fill.fore_color.rgb = fill
    if line is None:
        b.line.fill.background()
    else:
        b.line.color.rgb = line
        b.line.width = Pt(lw)
    b.shadow.inherit = False
    return b


def fit(sizes, build, avail):
    """First (largest) size whose block fits `avail` inches; else the last, flagged."""
    for size in sizes:
        res = build(size)
        if res[0] <= avail + 1e-6:
            return size, res, True
    return sizes[-1], res, False


# ---------------------------------------------------------------- template surgery
prs = Presentation(TPL)
if abs(prs.slide_width - Inches(13.333)) > Inches(0.01) or len(prs.slides) != 16:
    raise SystemExit('template changed: expected 16 slides at 13.333 x 7.5 in')
T = list(prs.slides)
S_TITLE, S_OUTLINE, S_THANKS, S_CHROME = T[0], T[1], T[15], T[3]
BLANK = next(lay for lay in prs.slide_layouts if lay.name == 'BLANK')


def _find(slide, pred, what):
    for sh in slide.shapes:
        if pred(sh):
            return sh
    raise SystemExit(f'template changed: {what} not found')


def _txt(sh):
    return sh.text_frame.text.strip() if sh.has_text_frame else ''


_rule = _find(S_CHROME, lambda sh: sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and sh.height < Inches(0.1)
              and abs(sh.top - Inches(1.73)) < Inches(0.05), 'orange rule')
_head = _find(S_CHROME, lambda sh: _txt(sh).startswith('Suggestions from Review'), 'red heading')
_logo = _find(S_CHROME, lambda sh: sh.shape_type == MSO_SHAPE_TYPE.PICTURE, 'PES logo')
_ptitle = _find(S_CHROME, lambda sh: _txt(sh) == 'Title of the Project', 'project-title box')
_foot = _find(S_CHROME, lambda sh: sh.is_placeholder and sh.placeholder_format.idx == 11, 'footer placeholder')
CHROME = {}
for key, sh in (('rule', _rule), ('heading', _head), ('logo', _logo), ('title', _ptitle), ('footer', _foot)):
    el = copy.deepcopy(sh._element)
    el[0].find(qn('p:cNvPr')).set('name', 'R3 ' + key)
    CHROME[key] = el
LOGO_PART = S_CHROME.part.related_part(_logo._element.blip_rId)
HEAD_RIGHT = (_head.left + _head.width) / 914400.0

# remove template slides 3-15: sldIdLst entry + the presentation's relationship to it
_lst = prs.slides._sldIdLst
for _sid in list(_lst)[2:15]:
    _rid = _sid.rId
    _lst.remove(_sid)
    prs.part.drop_rel(_rid)
prs.part.rename_slide_parts([sid.rId for sid in _lst])   # slide1..3, so new parts never collide


def _set_runs(el, text):
    """Put `text` in the first run of a copied shape and drop any other runs."""
    runs = list(el.iter(qn('a:r')))
    runs[0].find(qn('a:t')).text = text
    for r in runs[1:]:
        r.getparent().remove(r)


def _set_shape_text(slide, pred, text, what):
    _set_runs(_find(slide, pred, what)._element, text)


def _notes(s, presenter, text):
    tf = s.notes_slide.notes_text_frame
    if tf is None:
        warn('notes placeholder missing on a slide')
        return
    tf.text = f'[Presenter: {presenter}] ' + F(text)


def chrome(heading, takeaway=None):
    """New slide on the BLANK layout with the template's chrome; returns (slide, content top)."""
    s = prs.slides.add_slide(BLANK)
    tree = s.shapes._spTree
    els = {}
    for key in ('rule', 'heading', 'logo', 'title', 'footer'):
        els[key] = copy.deepcopy(CHROME[key])
        tree.append(els[key])
    els['logo'].find('.//' + qn('a:blip')).set(qn('r:embed'), s.part.relate_to(LOGO_PART, RT.IMAGE))
    _set_runs(els['title'], TITLE)
    _set_runs(els['footer'], FOOT)
    _set_runs(els['heading'], heading)
    xfrm = els['heading'].find('.//' + qn('a:xfrm'))
    xfrm.find(qn('a:off')).set('x', str(Inches(HEAD_X)))
    xfrm.find(qn('a:ext')).set('cx', str(Inches(HEAD_RIGHT - HEAD_X)))
    if text_w(heading, 24) > HEAD_RIGHT - HEAD_X - 0.25:
        for rpr in els['heading'].iter(qn('a:rPr')):
            rpr.set('sz', '2000')
        warn(f'heading shrunk to 20 pt: {heading}')
    if not takeaway:
        return s, REF_TOP
    tw = TAKE_R - X0

    def build(z):   # one line at the largest size that keeps it to one line (two only if it must)
        ps = [P(takeaway, z, RUST, bold=True, align=PP_ALIGN.RIGHT)]
        return ps_height(ps, tw), ps
    size, (h, ps), ok = fit((17, 16, 15), build, 17 * LH / 72 + 2 * INS_V + 1e-3)
    if not ok:
        warn(f'takeaway wraps to two lines: {takeaway}')
    add_text(s, X0, TAKE_Y, tw, h, ps)
    return s, TAKE_Y + h + 0.1


# ---------------------------------------------------------------- renderers
def _footer_ps(text, align=PP_ALIGN.LEFT):
    return [P(text, 14, DARK, italic=True, align=align)]


def r_bullets(s, sd, top):
    x, w = 0.8, X1 - 0.8
    foot = F(sd['footer']) if sd.get('footer') else None
    fh = ps_height(_footer_ps(foot), w) if foot else 0.0

    def build(z):
        ps = []
        if sd.get('intro'):
            ps.append(P(F(sd['intro']), z, BLACK, after=z * 0.8))
        for b in sd['bullets']:
            sub = b.startswith('  ')
            ps.append(P(F(b.strip()), z - (2 if sub else 0), BLACK, after=z * 0.6, bullet=True))
        return ps_height(ps, w), ps
    size, (h, ps), ok = fit((20, 19, 18, 17, 16, 15, 14), build, BOTTOM - top - (fh + 0.1 if foot else 0))
    if not ok:
        warn(f"{sd['id']}: bullets overflow at {size} pt")
    add_text(s, x, top, w, h, ps)
    if foot:
        add_text(s, x, top + h + 0.1, w, fh, _footer_ps(foot))


def row_heights(rows, widths, size):
    out = []
    for r, row in enumerate(rows):
        best = 0.0
        for c, w in zip(row, widths):
            parts = _md(c)
            if r == 0:
                parts = [(t, True) for t, _ in parts]
            parts = prep(parts, size, w - 2 * CM_LR)
            best = max(best, n_lines(parts, size, w - 2 * CM_LR) * size * LH / 72)
        out.append(best + 2 * CM_TB)
    return out


def add_table(s, rows, x, y, widths, heights, size):
    shp = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y),
                             Inches(sum(widths)), Inches(sum(heights)))
    t = shp.table
    t.first_row, t.horz_banding = True, False
    for i, w in enumerate(widths):
        t.columns[i].width = Inches(w)
    for i, h in enumerate(heights):
        t.rows[i].height = Inches(h)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            cell = t.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(CM_LR)
            cell.margin_top = cell.margin_bottom = Inches(CM_TB)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE if r == 0 else MSO_ANCHOR.TOP
            tf = cell.text_frame
            tf.word_wrap = True
            todo = r > 0 and v.startswith('[') and v.endswith(']')   # row the team fills in by hand
            parts = _md(v)
            if r == 0:
                parts = [(tt, True) for tt, _ in parts]
            col = WHITE if r == 0 else (GREY if todo else BLACK)
            for tt, b in prep(parts, size, widths[c] - 2 * CM_LR):
                _run(tf.paragraphs[0], tt, size, b, todo, col)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RUST if r == 0 else (LIGHT if r % 2 == 0 else WHITE)
    return shp


def _pdf_page(rel, page, dpi=150):
    """One page of a PDF as an in-memory PNG (PyMuPDF), so the deck can show a document page
    without writing an image file; returns (stream, width/height) or None if PyMuPDF is absent."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        warn(f'PyMuPDF not installed: {rel} page {page} not shown (pip install pymupdf)')
        return None
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        raise SystemExit(f'side page missing: {rel}')
    with fitz.open(path) as doc:
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        return io.BytesIO(pix.tobytes('png')), pix.width / pix.height


def r_table(s, sd, top):
    tb = sd['table']
    rows = [[typo(F(c)) for c in tb['header']]] + [[typo(F(c)) for c in row] for row in tb['rows']]
    x, bw = X0, BODY_W
    sp = sd.get('side_page')   # a document page (e.g. the IEEE draft's first page) left of the table
    page = _pdf_page(sp['pdf'], sp.get('page', 1)) if sp else None
    if page:
        png, ar = page
        cap = F(sp.get('caption') or '')
        pw = 3.6
        for _ in range(4):   # tallest page that leaves room for its caption above the band
            cap_h = ps_height([P(cap, 12, GREY, italic=True)], pw) if cap else 0.0
            ph = BOTTOM - top - cap_h - 0.04
            if abs(ph * ar - pw) < 1e-3:
                break
            pw = ph * ar
        pic = s.shapes.add_picture(png, Inches(X0), Inches(top), Inches(pw), Inches(ph))
        pic.line.color.rgb = PALE
        pic.line.width = Pt(0.75)
        if cap:
            add_text(s, X0, top + ph + 0.04, pw, cap_h, [P(cap, 12, GREY, italic=True)])
        x = X0 + pw + 0.3
        bw = X1 - x
    widths = tb.get('col_widths_in') or [bw / len(rows[0])] * len(rows[0])
    k = bw / sum(widths)
    widths = [w * k for w in widths]
    y = top
    if sd.get('intro'):
        ips = [P(F(sd['intro']), 15, BLACK)]
        ih = ps_height(ips, bw)
        add_text(s, x, y, bw, ih, ips)
        y += ih + 0.06
    foot = F(sd['footer']) if sd.get('footer') else None
    fh = ps_height(_footer_ps(foot), bw) if foot else 0.0
    avail = BOTTOM - y - (fh + 0.08 if foot else 0)

    def build(z):
        hs = row_heights(rows, widths, z)
        return sum(hs), hs
    size, (th, hs), ok = fit((14, 13.5, 13, 12.5, 12, 11.5, 11), build, avail)
    if not ok:
        warn(f"{sd['id']}: table needs {th:.2f} in, has {avail:.2f} in at {size} pt")
    add_table(s, rows, x, y, widths, hs, size)
    if foot:
        add_text(s, x, y + th + 0.08, bw, fh, _footer_ps(foot))


_INLINE_COMMENT = re.compile(r'^(.*?\S)(\s{2,}#.*)$')


def r_pseudocode(s, sd, top):
    code = sd['code']
    title = F(code['title'])
    lines = [F(ln) for ln in code['lines']]
    H = BOTTOM - top
    pad = 0.12
    tps = [P(F(sd.get('side_title') or 'In plain words'), 16, RUST, bold=True)]
    cps = [P('Code: ' + F(sd['code_ref']), 11, GREY, italic=True)] if sd.get('code_ref') else []

    def code_need(z):
        maxw = max(text_w(ln, z, font=MONO) for ln in lines)
        pw = min(max(maxw + 2 * pad + 2 * INS + 0.06, 5.8), 7.7)
        inner = pw - 2 * pad - 2 * INS
        nl = sum(max(1, math.ceil(text_w(ln, z, font=MONO) / inner - 1e-9)) for ln in lines)
        th = n_lines([(title, True)], 14, inner) * 14 * LH / 72 + 5 / 72
        return th + nl * z * LH / 72 + 2 * INS_V + 0.16, pw

    def side_fit(pw, sizes):
        sw = X1 - (X0 + pw + 0.3)
        avail = H - ps_height(tps, sw) - 0.04 - (ps_height(cps, sw) + 0.08 if cps else 0)
        return fit(sizes, lambda z: (ps_height(
            [P(F(b), z, BLACK, after=z * 0.55, bullet=True) for b in sd.get('side_bullets', [])], sw), z), avail)

    # largest code size whose panel leaves the explanation room at >= 15 pt, else >= 14 pt
    choice = None
    for side_sizes in ((17, 16, 15), (17, 16, 15, 14)):
        for cs in (13, 12.5, 12, 11.5, 11):
            need, pw = code_need(cs)
            if need <= H and side_fit(pw, side_sizes)[2]:
                choice = cs, pw
                break
        if choice:
            break
    if choice is None:
        cs, (need, pw) = 11, code_need(11)
        warn(f"{sd['id']}: code + explanation do not fit at the minimum sizes")
    else:
        cs, pw = choice
    ph = min(H, code_need(cs)[0] + 0.1)     # panel hugs the code
    add_box(s, X0, top, pw, ph, fill=CODEBG, line=ORANGE, lw=1.5, shape=MSO_SHAPE.RECTANGLE)
    box = s.shapes.add_textbox(Inches(X0 + pad), Inches(top + 0.08), Inches(pw - 2 * pad), Inches(ph - 0.16))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = Inches(INS)
    tf.margin_top = tf.margin_bottom = Inches(INS_V)
    p = tf.paragraphs[0]
    p.space_after = Pt(5)
    _run(p, title, 14, True, False, RUST)
    for ln in lines:
        p = tf.add_paragraph()
        if ln.lstrip().startswith('#'):
            _run(p, ln, cs, False, True, GREY, MONO)
            continue
        m = _INLINE_COMMENT.match(ln)
        _run(p, m.group(1) if m else ln, cs, False, False, BLACK, MONO)
        if m:
            _run(p, m.group(2), cs, False, True, GREY, MONO)
    # right: plain-words explanation, then where it lives in the code
    sx = X0 + pw + 0.3
    sw = X1 - sx
    tht = ps_height(tps, sw)
    add_text(s, sx, top, sw, tht, tps)
    if cps:
        ch = ps_height(cps, sw)
        add_text(s, sx, BOTTOM - ch, sw, ch, cps)
    z, (h, _), ok = side_fit(pw, (17, 16, 15, 14))
    ps = [P(F(b), z, BLACK, after=z * 0.55, bullet=True) for b in sd.get('side_bullets', [])]
    add_text(s, sx, top + tht + 0.04, sw, h, ps)


def _badge(s, x, y, d, n):
    """Orange disc with a white step number."""
    bd = add_box(s, x, y, d, d, ORANGE, None, shape=MSO_SHAPE.OVAL)
    tf = bd.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    _run(tf.paragraphs[0], str(n), 18 if d >= 0.48 else 16, True, False, WHITE)


def r_steps(s, sd, top):
    steps = sd['steps']
    if len(steps) >= 5:
        return r_flow(s, sd, top)
    n = len(steps)
    gap = 0.42
    bw = (BODY_W - gap * (n - 1)) / n
    inner = bw - 0.3
    foot = F(sd['footer']) if sd.get('footer') else None
    fh = ps_height(_footer_ps(foot, PP_ALIGN.CENTER), BODY_W) if foot else 0.0
    avail = BOTTOM - top - (fh + 0.14 if foot else 0)
    data = [(F(st['title']), F(st['body']), 'Result: ' + F(st['result'])) for st in steps]

    def build(z):
        ts, bs, rs = z
        hh = max(max(0.5, ps_height([P(t, ts, DARK, bold=True)], bw - 0.78)) for t, _, _ in data)
        bh = max(ps_height([P(b, bs, BLACK)], inner + 2 * INS) for _, b, _ in data)
        rh = max(ps_height([P(r, rs, RUST, bold=True)], inner - 0.1) for _, _, r in data) + 0.08
        return 0.1 + hh + 0.06 + bh + 0.14 + rh + 0.12, (hh, bh, rh)
    z, (need, (hh, bh, rh)), ok = fit(((18, 17, 15), (17, 16, 15), (16, 16, 15), (16, 15, 14), (15, 14, 14),
                                       (14, 14, 14)), build, avail)
    if not ok:
        warn(f"{sd['id']}: steps need {need:.2f} in, have {avail:.2f} in")
    ts, bs, rs = z
    box_h = min(avail, need + 0.15)
    for i, (t, b, r) in enumerate(data):
        x = X0 + (bw + gap) * i
        add_box(s, x, top, bw, box_h, LIGHT, ORANGE, 1.75, adj=0.06)
        _badge(s, x + 0.14, top + 0.1 + (hh - 0.44) / 2, 0.44, i + 1)
        add_text(s, x + 0.66, top + 0.1, bw - 0.78, hh, [P(t, ts, DARK, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, x + 0.15 - INS, top + 0.1 + hh + 0.06, inner + 2 * INS, bh, [P(b, bs, BLACK)])
        ry = top + box_h - 0.1 - rh
        add_box(s, x + 0.08, ry, bw - 0.16, rh, WHITE, PALE, 0.75, MSO_SHAPE.RECTANGLE)
        add_text(s, x + 0.13, ry + 0.04, bw - 0.26, rh - 0.08, [P(r, rs, RUST, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
        if i < n - 1:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + bw + 0.06), Inches(top + box_h / 2 - 0.16),
                                   Inches(gap - 0.12), Inches(0.32))
            a.fill.solid()
            a.fill.fore_color.rgb = ORANGE
            a.line.fill.background()
    if foot:
        add_text(s, X0, top + box_h + 0.14, BODY_W, fh, _footer_ps(foot, PP_ALIGN.CENTER))


def r_flow(s, sd, top):
    """Five or more steps: one numbered row per step, read top to bottom."""
    steps = sd['steps']
    n = len(steps)
    foot = F(sd['footer']) if sd.get('footer') else None
    fh = ps_height(_footer_ps(foot, PP_ALIGN.CENTER), BODY_W) if foot else 0.0
    avail = BOTTOM - top - (fh + 0.12 if foot else 0)
    badge = 0.5
    rx = X0 + badge + 0.18
    rw = X1 - rx
    c1, c3 = 2.55, 3.35
    c2 = rw - c1 - c3 - 0.5
    gap = 0.12
    data = [(F(st['title']), F(st['body']), '\u2192 ' + F(st['result'])) for st in steps]

    def build(z):
        ts, bs, rs = z
        hs = []
        for t, b, r in data:
            hs.append(max(ps_height([P(t, ts, DARK, bold=True)], c1), ps_height([P(b, bs, BLACK)], c2),
                          ps_height([P(r, rs, RUST, bold=True)], c3), badge) + 0.12)
        return sum(hs) + gap * (n - 1), hs
    z, (need, hs), ok = fit(((17, 17, 16), (16, 16, 15), (16, 15, 15), (15, 15, 14), (15, 14, 14), (14, 14, 14)),
                            build, avail)
    if not ok:
        warn(f"{sd['id']}: flow needs {need:.2f} in, has {avail:.2f} in")
    ts, bs, rs = z
    y = top
    centres = []
    for i, ((t, b, r), h) in enumerate(zip(data, hs)):
        add_box(s, rx, y, rw, h, LIGHT, ORANGE, 1.25, adj=0.12)
        by = y + (h - badge) / 2
        centres.append((by, by + badge))
        _badge(s, X0, by, badge, i + 1)
        cx = rx + 0.15
        add_text(s, cx, y, c1, h, [P(t, ts, DARK, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, cx + c1 + 0.1, y, c2, h, [P(b, bs, BLACK)], anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, cx + c1 + c2 + 0.2, y, c3, h, [P(r, rs, RUST, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
        y += h + gap
    for (a0, a1), (b0, b1) in zip(centres, centres[1:]):   # thin spine joining the numbers
        add_box(s, X0 + badge / 2 - 0.02, a1, 0.04, b0 - a1, ORANGE, None, shape=MSO_SHAPE.RECTANGLE)
    if foot:
        add_text(s, X0, y - gap + 0.12, BODY_W, fh, _footer_ps(foot, PP_ALIGN.CENTER))


def r_twocol(s, sd, top):
    cols = sd['cols'][:2]
    gap = 0.3
    cw = (BODY_W - gap) / 2
    inner = cw - 0.36
    foot = F(sd['footer']) if sd.get('footer') else None
    fh = ps_height(_footer_ps(foot, PP_ALIGN.CENTER), BODY_W) if foot else 0.0
    avail = BOTTOM - top - (fh + 0.12 if foot else 0)

    def build(z):
        th = max(ps_height([P(F(c['title']), z + 1, RUST, bold=True)], inner) for c in cols)
        bh = max(ps_height([P(F(b), z, BLACK, after=z * 0.55, bullet=True) for b in c['bullets']], inner)
                 for c in cols)
        return 0.1 + th + 0.04 + bh + 0.1, (th, bh)
    z, (need, (th, bh)), ok = fit((18, 17, 16, 15, 14), build, avail)
    if not ok:
        warn(f"{sd['id']}: columns need {need:.2f} in, have {avail:.2f} in")
    box_h = min(avail, need + 0.12)
    for i, c in enumerate(cols):
        x = X0 + (cw + gap) * i
        add_box(s, x, top, cw, box_h, LIGHT, ORANGE, 1.75, adj=0.04)
        add_text(s, x + 0.18, top + 0.1, inner, th, [P(F(c['title']), z + 1, RUST, bold=True)])
        add_text(s, x + 0.18, top + 0.1 + th + 0.04, inner, bh,
                 [P(F(b), z, BLACK, after=z * 0.55, bullet=True) for b in c['bullets']])
    if foot:
        add_text(s, X0, top + box_h + 0.12, BODY_W, fh, _footer_ps(foot, PP_ALIGN.CENTER))


def r_chart(s, sd, top):
    ch = sd['chart']
    path = os.path.join(ROOT, ch['image'])
    if not os.path.exists(path):
        raise SystemExit(f"{sd['id']}: chart image missing: {ch['image']}")
    with Image.open(path) as im:
        ar = im.size[0] / im.size[1]
    cap = F(ch.get('caption') or '')
    w = 7.4
    for _ in range(4):   # widest image that leaves room for its caption above the band
        cap_h = ps_height([P(cap, 12, GREY, italic=True)], w) if cap else 0.0
        maxh = BOTTOM - top - cap_h - 0.04
        if w / ar <= maxh + 1e-6:
            break
        w = maxh * ar
    h = w / ar
    pic = s.shapes.add_picture(path, Inches(X0), Inches(top), Inches(w), Inches(h))
    pic.line.color.rgb = PALE
    pic.line.width = Pt(0.75)
    if cap:
        add_text(s, X0, top + h + 0.04, w, cap_h, [P(cap, 12, GREY, italic=True)])
    sx = X0 + w + 0.35
    sw = X1 - sx
    foot = F(sd['footer']) if sd.get('footer') else None
    fps = [P(foot, 14, DARK, bold=True, italic=True)] if foot else []
    fh = ps_height(fps, sw - 0.2) + 0.1 if foot else 0.0
    avail = BOTTOM - top - (fh + 0.15 if foot else 0)

    def side(z):
        ps = [P(F(b), z, BLACK, after=z * 0.6, bullet=True) for b in sd.get('side_bullets', [])]
        return ps_height(ps, sw), ps
    z, (bh, ps), ok = fit((18, 17, 16, 15, 14), side, avail)
    if not ok:
        warn(f"{sd['id']}: chart side text needs {bh:.2f} in, has {avail:.2f} in")
    add_text(s, sx, top, sw, bh, ps)
    if foot:
        fy = top + bh + 0.15
        add_box(s, sx, fy, sw, fh, LIGHT, None, shape=MSO_SHAPE.RECTANGLE)
        add_box(s, sx, fy, 0.06, fh, ORANGE, None, shape=MSO_SHAPE.RECTANGLE)
        add_text(s, sx + 0.15, fy + 0.05, sw - 0.2, fh - 0.1, fps, anchor=MSO_ANCHOR.MIDDLE)


RENDER = {'bullets': r_bullets, 'table': r_table, 'pseudocode': r_pseudocode, 'steps': r_steps,
          'twocol': r_twocol, 'chart': r_chart}


# ---------------------------------------------------------------- references (IEEE), auto-paginated
REF_HANG = 0.55


def ref_pages(refs, size, target=None):
    """Greedy pages of [n] entries; with `target`, break near that height to balance pages."""
    avail = BOTTOM - REF_TOP
    pages, cur, h = [], [], 2 * INS_V
    for i, r in enumerate(refs, 1):
        pd = P(r, size, BLACK, after=4, label=f'[{i}]', hang=REF_HANG)
        rh = p_height(pd, BODY_W - 2 * INS)
        limit = avail if target is None else min(avail, target + rh / 2)
        if cur and h + rh > limit:
            pages.append(cur)
            cur, h = [], 2 * INS_V
        cur.append(pd)
        h += rh
    if cur:
        pages.append(cur)
    return pages


def references():
    refs = [F(r) for r in json.load(open(os.path.join(SRC, '90_references.json'), encoding='utf-8'))['references']]
    best = None
    for size in (12, 11.5, 11):
        pages = ref_pages(refs, size)
        if best is None or len(pages) < len(best[1]):
            best = (size, pages)
    size, pages = best
    total = sum(p_height(pd, BODY_W - 2 * INS) for page in pages for pd in page)
    balanced = ref_pages(refs, size, target=total / len(pages))
    if len(balanced) == len(pages):
        pages = balanced
    for k, page in enumerate(pages):
        s, top = chrome('References' if k == 0 else 'References (continued)')
        add_text(s, X0, top, BODY_W, BOTTOM - top, page)
        _notes(s, 'Kaustubh', 'IEEE format. Do not read these out: point at the slide, say the full '
               'details are in the report, and move on.' if k == 0 else 'IEEE format, continued.')
    return len(pages), size


# ---------------------------------------------------------------- kept template slides
def fill_title_slide(s):
    _set_shape_text(s, lambda sh: _txt(sh) == 'Title of the Project', TITLE, 'title-slide project title')
    _set_shape_text(s, lambda sh: sh.is_placeholder and sh.placeholder_format.idx == 11, FOOT, 'title-slide footer')
    lab = _find(s, lambda sh: _txt(sh).startswith('Project Title'), 'title-slide labels')
    body = lab.text_frame._txBody
    paras = body.findall(qn('a:p'))
    pPr0 = copy.deepcopy(paras[0].find(qn('a:pPr')))
    rPr0 = copy.deepcopy(paras[0].find(qn('a:r')).find(qn('a:rPr')))
    for p in paras:
        body.remove(p)
    size = 22
    rPr0.set('sz', str(size * 100))
    labels = ['Project Title', 'Project ID', 'Project Guide', 'Project Team']
    t1 = max(text_w(lbl, size) for lbl in labels) + 0.3
    t2 = t1 + text_w(':', size) + 0.3
    rows = list(zip(labels, [TITLE, PROJECT_ID, GUIDE, TEAM[0]])) + [('', m) for m in TEAM[1:]]
    for label, value in rows:
        p = etree.SubElement(body, qn('a:p'))
        pPr = copy.deepcopy(pPr0)
        p.append(pPr)
        tabs = etree.Element(qn('a:tabLst'))
        for pos in (t1, t2):
            etree.SubElement(tabs, qn('a:tab'), pos=str(Inches(pos)), algn='l')
        nxt = [c for c in pPr if c.tag in (qn('a:defRPr'), qn('a:extLst'))]
        if nxt:
            nxt[0].addprevious(tabs)
        else:
            pPr.append(tabs)
        r = etree.SubElement(p, qn('a:r'))
        r.append(copy.deepcopy(rPr0))
        etree.SubElement(r, qn('a:t')).text = (f'{label}\t:\t' if label else '\t\t') + value
    lab.left, lab.top, lab.width, lab.height = Inches(1.6), Inches(3.0), Inches(10.6), Inches(2.85)
    _notes(s, 'Vidisha', f'Good morning. We are team {PROJECT_ID}, guided by {GUIDE}. Our project is the '
           f'{TITLE}. Each of us presents what we built: Kaustubh the models and validation; Khushee the '
           'ChildApp, capture and the live demo; Kanak the backend, deployment and testing; and I the '
           'ParentApp, ethics and applicability.')


def fill_outline_slide(s):
    _set_shape_text(s, lambda sh: _txt(sh) == 'Title of the Project', TITLE, 'outline project title')
    _set_shape_text(s, lambda sh: sh.is_placeholder and sh.placeholder_format.idx == 11, FOOT, 'outline footer')
    head = _find(s, lambda sh: _txt(sh) == 'Outline', 'outline heading')   # line it up with every other heading
    head.left, head.top = Inches(HEAD_RIGHT) - head.width, _head.top
    # The template's outline list omits three sections its own section table prescribes
    # (docs/templates/REVIEW3_REQUIREMENTS.md rows 8, 9, 13) and this deck presents; list them
    # in deck order, as copies of the template's own bullet paragraphs, at a size that fits 14.
    box = _find(s, lambda sh: 'Abstract' in _txt(sh) and 'Results and Discussion' in _txt(sh), 'outline list')

    def _insert_after(label, text):
        anchor = next((p for p in box.text_frame.paragraphs if p.text.strip() == label), None)
        if anchor is None:
            raise SystemExit(f'template changed: outline item {label!r} not found')
        el = copy.deepcopy(anchor._p)
        runs = el.findall(qn('a:r'))
        for r in runs[1:]:
            el.remove(r)
        runs[0].find(qn('a:t')).text = text
        anchor._p.addnext(el)

    _insert_after('Results and Discussion', 'Applicability of Proposed Methodology in Other Domains')
    _insert_after('Applicability of Proposed Methodology in Other Domains', 'Timeline – Update on Tasks')
    _insert_after('List of Targeted Conferences/Journals', 'Any Other Information')
    for p in box.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(18)
    _notes(s, 'Vidisha', "We follow the department's Review 3 template in order: the abstract, what we did with "
           'the Review 2 suggestions, implementation, the live demonstration, the test plan, results, '
           'applicability to other domains, the timeline and the report, conclusion, references, the IEEE '
           'draft and the venues we are targeting.')


def fill_thanks_slide(s):
    ty = _find(s, lambda sh: 'Thank' in _txt(sh), 'Thank You text')
    ty.left, ty.width = Inches((SW - 5.0) / 2), Inches(5.0)
    for p in ty.text_frame.paragraphs:
        p.alignment = PP_ALIGN.CENTER
    el = copy.deepcopy(CHROME['footer'])
    s.shapes._spTree.append(el)
    _set_runs(el, FOOT)
    _notes(s, 'Kanak', 'Thank the panel and invite questions; each of us answers for the modules we built.')


# ---------------------------------------------------------------- build
def load_slides():
    out = []
    for f in sorted(glob.glob(os.path.join(SRC, '*.json'))):
        if os.path.basename(f).startswith('90_'):
            continue
        data = json.load(open(f, encoding='utf-8'))
        out += data if isinstance(data, list) else data['slides']
    ids = [sd['id'] for sd in out]
    if len(set(ids)) != len(ids):
        raise SystemExit('duplicate slide ids in docs/review3')
    return sorted(out, key=lambda sd: sd['order'])


def check_geometry():
    n = len(prs.slides)
    for i, s in enumerate(prs.slides, 1):
        if i in (1, 2, n):
            continue
        for sh in s.shapes:
            if sh.name.startswith('R3 ') or sh.is_placeholder:
                continue
            top, bot = sh.top / 914400, (sh.top + sh.height) / 914400
            if bot > BAND_TOP - 0.05:
                warn(f'slide {i}: {sh.name} reaches {bot:.2f} in (band at {BAND_TOP})')
            if top < RULE_BOTTOM:
                warn(f'slide {i}: {sh.name} starts at {top:.2f} in, above the rule')


def main():
    slides = load_slides()
    fill_title_slide(S_TITLE)
    fill_outline_slide(S_OUTLINE)
    fill_thanks_slide(S_THANKS)
    n_ref, ref_size = 0, 0
    for sd in slides:
        if sd['order'] > 730 and not n_ref:
            n_ref, ref_size = references()
        if sd['kind'] not in RENDER:
            raise SystemExit(f"{sd['id']}: unknown kind {sd['kind']!r}")
        s, top = chrome(F(sd['heading']), F(sd['subheading']) if sd.get('subheading') else None)
        RENDER[sd['kind']](s, sd, top)
        _notes(s, sd['presenter'], sd.get('notes', ''))
    if not n_ref:
        n_ref, ref_size = references()
    # Thank You last
    lst = prs.slides._sldIdLst
    ty = next(sid for sid in lst if prs.part.related_part(sid.rId) is S_THANKS.part)
    lst.remove(ty)
    lst.append(ty)
    prs.part.rename_slide_parts([sid.rId for sid in lst])
    check_geometry()
    prs.save(ARGS.out)

    print(f'wrote {ARGS.out}  ({len(prs.slides)} slides; {len(slides)} content + {n_ref} references '
          f'at {ref_size} pt + title, outline, thank-you){"  [PREVIEW]" if PENDING else ""}')
    tot = {}
    for sd in slides:
        a = tot.setdefault(sd['presenter'], [0, 0, 0, 0])
        a[0] += sd['seconds']
        a[1] += 1
        if not sd.get('skip_if_short'):
            a[2] += sd['seconds']
            a[3] += 1
    for who, (sec, n, sec_ns, n_ns) in sorted(tot.items(), key=lambda kv: -kv[1][0]):
        print(f'  {who:9s} {sec:5d} s ({n} slides)   non-skippable {sec_ns:5d} s ({n_ns})')
    print(f"  {'total':9s} {sum(a[0] for a in tot.values()):5d} s   non-skippable "
          f"{sum(a[2] for a in tot.values()):5d} s")
    for w in WARN:
        print('WARNING:', w)


if __name__ == '__main__':
    main()
