# -*- coding: utf-8 -*-
"""Build the Phase-3 project report (department format) from docs/report/*.md.

    python tools/build_report_docx.py --preview   # draft: gaps become highlighted markers
    python tools/build_report_docx.py             # final: every gap is an error
    python tools/finalize_report.py               # Word: TOC + page numbers, then the PDF
    python tools/build_report_docx.py --refresh-refs   # rebuild docs/report/references.json

Sources (one Markdown-like file per chapter, format in docs/report/README.md):
    00_acknowledgement.md, 00_abstract.md            front matter
    01_introduction.md ... 09_conclusion.md          chapters 1-9
    appendix_a_abbreviations.md, appendix_b_user_manual.md
    references.json (+ references_extra_*.json)      bibliography, IEEE plain text

Output: docs/CAPSTONE_REPORT.docx laid out as the department asks (A4, 2 cm margins,
Times New Roman 12 pt at 1.5 spacing, chapter-wise numbering, header from Chapter 1 with
project title and PES logo, footer "Dept. of CSE | Aug - Dec 2026 | page"), with the
initial pages reproduced from docs/templates/report_initial_pages/*.docx.

python-docx cannot paginate, so the table of contents, the lists of figures/tables and
the page numbers are Word fields; tools/finalize_report.py makes Word compute them.

Numbers are never typed into the sources: {key} placeholders are filled from
tools/project_numbers.py. A final build (no --preview) fails, listing file:line, on any
unknown number key, unknown citation or cross-reference, missing figure, missing chapter
or broken format rule, so the report cannot silently drift from the committed results.
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata
import zipfile

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import (WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_LINE_SPACING,
                            WD_TAB_ALIGNMENT, WD_TAB_LEADER)
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project_numbers as PN  # noqa: E402  (one source of truth for every number)

# --------------------------------------------------------------------------- paths
ROOT = PN.ROOT
DOCS = os.path.join(ROOT, 'docs')
REPORT_SRC = os.path.join(DOCS, 'report')
FIG_DIR = os.path.join(DOCS, 'figures', 'report')
OUT_DOCX = os.path.join(DOCS, 'CAPSTONE_REPORT.docx')
TEMPLATE_DIR = os.path.join(DOCS, 'templates', 'report_initial_pages')
LOGO = os.path.join(FIG_DIR, 'pes_logo.png')     # extracted from the department template
LOGO_SOURCE = (os.path.join(TEMPLATE_DIR, 'p10_body_pages.docx'), 'word/media/image1.png')
BIB_SOURCES = [os.path.join(DOCS, 'PROJECT_PAPER.tex'), os.path.join(DOCS, 'ieee_refs.tex')]

# --------------------------------------------------------------------------- report facts
PROJECT_TITLE = 'AI-Driven Gaming Addiction Screening System'
COURSE = 'UE23CS441A'
TEAM = [('Kaustubh Agarwal', 'PES1UG23CS291'), ('Khushee P Kiran', 'PES1UG23CS303'),
        ('Kanak Goyal', 'PES1UG23CS279'), ('Vidisha Murali', 'PES1UG23CS681')]
GUIDE = 'Prof. Shridevi Sawant'
# Not recorded anywhere in the repository: confirm with the guide, then write it here
# (e.g. 'Assistant Professor'). While None, the pages print a yellow "Designation".
GUIDE_DESIGNATION = 'Professor'
PERIOD = 'August – Dec, 2026'          # wording of the title-page/certificate/declaration templates
FOOTER_PERIOD = 'Aug – Dec 2026'       # wording the guidelines give for the running footer
CHAPTER_LABEL = 'CHAPTER {n}'          # the p09 template prints 'CHAPTER-1'; change here if asked

FRONT = [('ack', '00_acknowledgement.md'), ('abstract', '00_abstract.md')]
CHAPTERS = [('1', '01_introduction.md'), ('2', '02_problem_statement.md'),
            ('3', '03_literature_review.md'), ('4', '04_requirements.md'),
            ('5', '05_system_design.md'), ('6', '06_methodology.md'),
            ('7', '07_implementation.md'), ('8', '08_results.md'), ('9', '09_conclusion.md')]
APPENDICES = [('A', 'appendix_a_abbreviations.md'), ('B', 'appendix_b_user_manual.md')]

# --------------------------------------------------------------------------- format
BODY_FONT = 'Times New Roman'
TITLE_FONT = 'Arial'                   # the title-page and certificate templates use Arial
CODE_FONT = 'Consolas'
PAGE_W, PAGE_H, MARGIN = 21.0, 29.7, 2.0          # cm, A4
TEXT_W = PAGE_W - 2 * MARGIN                       # 17 cm
# cm from the page edge. The header (logo + rule) must end above the 2 cm top margin,
# or Word pushes the first body line down against the rule.
HEADER_DIST, FOOTER_DIST = 0.7, 1.0
BODY_PT, H1_PT, H2_PT, H3_PT, H4_PT = 12, 18, 16, 14, 12
TABLE_PT, TABLE_CODE_PT, CODE_PT, CAPTION_PT = 10.5, 9.5, 9.5, 11
INLINE_CODE_PT = 10.5
LOGO_HEADER_H = 0.8                                # cm
DEFAULT_FIG_W, MAX_FIG_W, MAX_FIG_H = 15.0, 16.0, 20.0
MAX_CODE_LINES, MAX_CODE_CHARS, MAX_TABLE_COLS = 40, 90, 6
ABSTRACT_MAX_WORDS = 150
KEEP_TABLE_TOGETHER_ROWS = 25                      # shorter tables never split across pages
KEEP_TABLE_MAX_CM = 10.0                            # ...unless taller than this: a tall table
                                                    # kept whole leaves up to a blank page
                                                    # behind it, so it splits between rows
                                                    # with its header row repeated
GREY_FILL, CODE_FILL, BORDER_GREY = 'D9D9D9', 'F2F2F2', '808080'
BLACK = RGBColor(0, 0, 0)
PENDING = '[pending]'

# Survey numbers that were superseded when the survey closed at its final sample;
# quoting any of them is a project rule violation (docs/DEFENSE_NOTES.md).
SUPERSEDED_RE = re.compile(
    r'(?<![\d.])0\.352(?!\d)|(?<![\d.])0\.349(?!\d)|\+0\.195(?!\d)|(?<![\d.])98\.6\s?%'
    r'|(?<![\d.])0\.491(?!\d)|\bn\s*=\s*87\b')


# =========================================================================== problems
class Problems:
    """Collects every problem with its file:line so that one run reports all of them.

    errors - the source is broken (unknown construct, duplicate label, abstract too long):
             fatal in every mode.
    gaps   - content is missing or breaks a format limit (chapter not written yet, unknown
             citation or cross-reference, missing figure, long code line): fatal in a final
             build; in --preview a warning, and the document shows a yellow marker.
    notes  - information only (fill-ins the team must make before printing)."""

    def __init__(self):
        self.errors, self.gaps, self.notes = [], [], []

    @staticmethod
    def _add(bucket, where, msg):
        line = f'{where}: {msg}' if where else msg
        if line not in bucket:
            bucket.append(line)

    def error(self, where, msg):
        self._add(self.errors, where, msg)

    def gap(self, where, msg):
        self._add(self.gaps, where, msg)

    def note(self, msg):
        self._add(self.notes, '', msg)


# =========================================================================== references
BIBITEM_RE = re.compile(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}')
_ACCENT_SYM = {"'": '\u0301', '`': '\u0300', '^': '\u0302', '"': '\u0308', '~': '\u0303',
               '=': '\u0304', '.': '\u0307'}
_ACCENT_LET = {'u': '\u0306', 'v': '\u030c', 'H': '\u030b', 'c': '\u0327', 'k': '\u0328'}
_SPECIAL_LETTERS = {'o': 'ø', 'O': 'Ø', 'ss': 'ß', 'aa': 'å', 'AA': 'Å', 'ae': 'æ',
                    'AE': 'Æ', 'l': 'ł', 'L': 'Ł', 'i': 'ı'}


def tex_to_text(s):
    """One \\bibitem body (LaTeX) -> plain-text IEEE string."""
    s = re.sub(r'(?<!\\)%[^\n]*', '', s)                  # comments
    s = ' '.join(s.split())
    s = s.replace('\\ ', ' ').replace('\\,', ' ').replace('\\@', '')
    s = re.sub(r'\\url\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\href\{([^}]*)\}\{([^}]*)\}', r'\2 (\1)', s)

    def accent(m):
        mark = _ACCENT_SYM.get(m.group(1)) or _ACCENT_LET.get(m.group(1))
        letter = m.group(2) or m.group(3)
        return unicodedata.normalize('NFC', letter + mark)
    # \v{s}, \c{c} (letter accents need braces); \'a, \'{a}, \'{\i} (symbol accents)
    s = re.sub(r'\\([uvHck])\{\\?([A-Za-z])\}()', accent, s)
    s = re.sub(r'\\([\'`^"~=.])(?:\{\\?([A-Za-z])\}|\\?([A-Za-z]))', accent, s)
    s = re.sub(r'\\(ss|aa|AA|ae|AE|[oOlLi])(?![A-Za-z])\{?\}?',
               lambda m: _SPECIAL_LETTERS[m.group(1)], s)
    for _ in range(3):                                      # nested formatting commands
        s = re.sub(r'\\(?:emph|textit|textbf|texttt|textsc|textrm|textsf|textup|mbox|text)'
                   r'\{([^{}]*)\}', r'\1', s)
    for a, b in (('\\&', '&'), ('\\%', '%'), ('\\_', '_'), ('\\#', '#'), ('\\$', '\x00')):
        s = s.replace(a, b)
    s = re.sub(r'\$([^$]*)\$', r'\1', s).replace('\x00', '$')  # inline math such as $11{,}191$
    s = s.replace('{,}', ',')
    s = s.replace('---', '—').replace('--', '–')
    s = s.replace('``', '“').replace("''", '”').replace('`', '‘').replace("'", '’')
    s = s.replace('~', ' ')
    s = re.sub(r'\\[A-Za-z]+\*?', '', s)                    # any other command (\small, ...)
    s = s.replace('{', '').replace('}', '').replace('\\', '')
    return unicodedata.normalize('NFC', ' '.join(s.split()))


def tex_bibitems(path):
    """{key: plain text} for every \\bibitem in a .tex file, in source order."""
    with open(path, encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'\\begin\{thebibliography\}[^\n]*\n(.*?)\\end\{thebibliography\}', text, re.S)
    body = m.group(1) if m else text
    parts = BIBITEM_RE.split(body)
    return {k.strip(): tex_to_text(v) for k, v in zip(parts[1::2], parts[2::2])}


def refs_from_tex():
    """Merge the bibliographies; a later source wins for a key both define (ieee_refs.tex
    holds the curated IEEE versions)."""
    refs = {}
    for path in BIB_SOURCES:
        if os.path.exists(path):
            refs.update(tex_bibitems(path))
    return refs


def refresh_refs(out_path):
    refs = refs_from_tex()
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(refs, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'wrote {os.path.relpath(out_path, ROOT)}: {len(refs)} references from '
          + ', '.join(os.path.relpath(p, ROOT) for p in BIB_SOURCES))


def load_refs(src, probs):
    """references.json (+ every references_extra_*.json) -> {key: IEEE string}."""
    main = os.path.join(src, 'references.json')
    if not os.path.exists(main):
        main = os.path.join(REPORT_SRC, 'references.json')
    if os.path.exists(main):
        with open(main, encoding='utf-8') as f:
            refs = json.load(f)
    else:
        refs = refs_from_tex()
        probs.note('docs/report/references.json is missing - built from the .tex '
                   'bibliographies in memory (run --refresh-refs to save it)')
    origin = {k: os.path.basename(main) for k in refs}
    for path in sorted(glob.glob(os.path.join(src, 'references_extra_*.json'))):
        name = os.path.basename(path)
        try:
            with open(path, encoding='utf-8') as f:
                extra = json.load(f)
        except ValueError as e:
            probs.error(name, f'not valid JSON ({e})')
            continue
        if not isinstance(extra, dict):
            probs.error(name, 'must be one JSON object {"key": "IEEE-style reference"}')
            continue
        for k, v in extra.items():
            if not isinstance(v, str) or not v.strip():
                probs.error(name, f'reference "{k}" must be a non-empty string')
            elif k in refs and refs[k] != v:
                probs.error(name, f'key "{k}" is already defined in {origin[k]} with '
                                  'different text - cite that entry, or pick a new key')
            else:
                refs[k], origin[k] = v.strip(), name
    return refs


# =========================================================================== source model
class Unit:
    """One source file: front matter, a chapter or an appendix."""

    def __init__(self, kind, num, fname):
        self.kind, self.num, self.fname = kind, num, fname   # kind: front|chapter|appendix
        self.title, self.title_label, self.title_line = '', None, 1
        self.blocks = []
        self.present = False

    @property
    def prefix(self):            # label prefix: ch6, appb
        return f'ch{self.num}' if self.kind == 'chapter' else f'app{self.num.lower()}'

    @property
    def display(self):
        return f'Chapter {self.num}' if self.kind == 'chapter' else f'Appendix {self.num}'


HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
TABLE_CAP_RE = re.compile(r'^Table:\s*(.+?)\s*$')
CODE_CAP_RE = re.compile(r'^(Algorithm|Listing):\s*(.+?)\s*$')
FIGURE_RE = re.compile(r'^!\[(?P<cap>[^\]]+)\]\((?P<path>[^)\s]+)\)(?P<attrs>\{[^}]*\})?\s*$')
EQUATION_RE = re.compile(r'^\$\$\s*(?P<body>.+?)\s*\$\$\s*(?P<attrs>\{[^}]*\})?\s*$')
LIST_RE = re.compile(r'^(?P<indent> *)(?P<marker>-|\d+\.)\s+(?P<text>\S.*)$')
FENCE_RE = re.compile(r'^```[\w+#.-]*\s*$')
SEPARATOR_RE = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$')
LABEL_TAIL_RE = re.compile(r'\s*\{#([^}\s]*)\}\s*$')
LABEL_RE = re.compile(r'^(sec|fig|tab|eq|alg|lst):((ch[1-9]|app[a-z])-[A-Za-z0-9][A-Za-z0-9_-]*)$')
NUMBERED_TITLE_RE = re.compile(r'^(\d+(\.\d+)*\.?|[A-Z](\.\d+)+\.?)\s')
REF_ITEM_RE = re.compile(r'^\s*@(cite|sec|fig|tab|eq|alg|lst):([A-Za-z0-9_.:-]+)\s*$')
FORBIDDEN_LINES = [
    (re.compile(r'^\s*>'), 'block quotes are not supported'),
    (re.compile(r'^\s*[*+]\s'), 'bullet lists use "- item"'),
    (re.compile(r'^(    |\t)'), 'indented blocks are not supported (nested list items indent '
                                'by two spaces; code goes in a captioned ``` fence)'),
    (re.compile(r'^\s*(-{3,}|\*{3,}|_{3,}|={3,})\s*$'), 'horizontal rules and setext headings '
                                                       'are not supported'),
    (re.compile(r'^\s*<'), 'raw HTML is not allowed'),
    (re.compile(r'^\s*\\[A-Za-z]'), 'LaTeX commands are not allowed'),
    (re.compile(r'^\s*\[\^'), 'footnotes are not supported'),
]


def is_block_start(line):
    s = line.strip()
    return bool(HEADING_RE.match(s) or TABLE_CAP_RE.match(s) or CODE_CAP_RE.match(s)
                or s.startswith(('|', '![', '$$', '```')) or LIST_RE.match(line.rstrip()))


def split_row(s):
    s = s.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    return [c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', s)]


class Parser:
    """Line-based parser for the report source format (docs/report/README.md)."""

    def __init__(self, unit, probs):
        self.u, self.p = unit, probs

    def where(self, ln):
        return f'{self.u.fname}:{ln}'

    def label(self, text, kinds, ln):
        """Split a trailing {#kind:label}; validate kind and chapter prefix."""
        m = LABEL_TAIL_RE.search(text)
        if not m:
            return text.strip(), None
        label, text = m.group(1), text[:m.start()].rstrip()
        mm = LABEL_RE.match(label)
        if self.u.kind == 'front':
            self.p.error(self.where(ln), f'labels are not allowed in front matter ({{#{label}}})')
            return text, None
        if not mm:
            self.p.error(self.where(ln), f'malformed label {{#{label}}} - expected '
                                         f'{{#{kinds[0]}:{self.u.prefix}-name}}')
            return text, None
        if mm.group(1) not in kinds:
            self.p.error(self.where(ln), f'label {{#{label}}} has the wrong kind here - '
                                         f'use {" or ".join(k + ":" for k in kinds)}')
            return text, None
        if mm.group(3) != self.u.prefix:
            self.p.error(self.where(ln), f'label {{#{label}}} must carry this file\'s prefix '
                                         f'"{self.u.prefix}-" ({mm.group(1)}:{self.u.prefix}-...)')
            return text, None
        return text, label

    def parse(self, text):
        u, lines = self.u, text.splitlines()
        if not lines or not lines[0].startswith('# '):
            self.p.error(self.where(1), 'the first line must be "# Chapter Title"')
            return
        u.title, u.title_label = self.label(lines[0][2:], ('sec',), 1)
        if NUMBERED_TITLE_RE.match(u.title):
            self.p.error(self.where(1), 'never type numbers in titles - the builder numbers them')
        i, n = 1, len(lines)
        while i < n:
            line = lines[i].rstrip()
            ln = i + 1
            s = line.strip()
            if not s:
                i += 1
                continue
            m = HEADING_RE.match(s)
            if m:
                self.heading(len(m.group(1)), m.group(2), ln)
                i += 1
                continue
            m = CODE_CAP_RE.match(s)
            if m:
                i = self.code(m, lines, i)
                continue
            if s.startswith('```'):
                self.p.error(self.where(ln), 'a code block needs a caption line ("Algorithm: '
                                             '..." or "Listing: ...") directly above the fence')
                j = i + 1
                while j < n and lines[j].strip() != '```':
                    j += 1
                i = j + 1
                continue
            m = TABLE_CAP_RE.match(s)
            if m:
                i = self.table(m, lines, i)
                continue
            if s.startswith('|'):
                self.p.error(self.where(ln), 'pipe table without a "Table: Caption {#tab:...}" '
                                             'line directly above it')
                while i < n and lines[i].strip().startswith('|'):
                    i += 1
                continue
            if s.startswith('!['):
                self.figure(s, ln)
                i += 1
                continue
            if s.startswith('$$'):
                self.equation(s, ln)
                i += 1
                continue
            bad = next((msg for rx, msg in FORBIDDEN_LINES if rx.match(line)), None)
            if bad:
                self.p.error(self.where(ln), f'{bad}: {s[:60]!r}')
                i += 1
                continue
            if LIST_RE.match(line):
                i = self.list_block(lines, i)
                continue
            i = self.paragraph(lines, i)

    def heading(self, level, raw, ln):
        if level == 1:
            self.p.error(self.where(ln), 'only the first line may be a "# " title; use ## for '
                                         'sections')
            return
        if level > 4:
            self.p.error(self.where(ln), f'{"#" * level} headings are not supported (## section,'
                                         ' ### subsection, #### unnumbered heading)')
            return
        text, label = self.label(raw, ('sec',), ln)
        if level == 4 and label:
            self.p.error(self.where(ln), '#### headings are unnumbered and cannot carry a label')
            label = None
        if NUMBERED_TITLE_RE.match(text):
            self.p.error(self.where(ln), f'never type numbers in headings: {text[:40]!r}')
        if self.u.kind == 'front':
            self.p.error(self.where(ln), 'front matter has no headings')
            return
        self.u.blocks.append(dict(t=f'h{level}', line=ln, text=text, label=label))

    def code(self, m, lines, i):
        ln, n = i + 1, len(lines)
        kind = 'alg' if m.group(1) == 'Algorithm' else 'lst'
        cap, label = self.label(m.group(2), (kind,), ln)
        if i + 1 >= n or not FENCE_RE.match(lines[i + 1].strip()):
            self.p.error(self.where(ln), f'"{m.group(1)}:" caption must be followed directly '
                                         'by a ``` fence')
            return i + 1
        j, code = i + 2, []
        while j < n and lines[j].strip() != '```':
            code.append(lines[j].rstrip().expandtabs(4))
            j += 1
        if j >= n:
            self.p.error(self.where(i + 2), 'code fence is never closed with ```')
            return n
        if not any(c.strip() for c in code):
            self.p.error(self.where(ln), 'empty code block')
        if len(code) > MAX_CODE_LINES:
            self.p.gap(self.where(ln), f'code block has {len(code)} lines (limit '
                                       f'{MAX_CODE_LINES}) - shorten or split it')
        for k, c in enumerate(code):
            if len(c) > MAX_CODE_CHARS:
                self.p.gap(self.where(i + 3 + k), f'code line is {len(c)} characters (limit '
                                                  f'{MAX_CODE_CHARS})')
        self.u.blocks.append(dict(t='code', kind=kind, line=ln, caption=cap, label=label,
                                  lines=code))
        return j + 1

    def table(self, m, lines, i):
        ln, n = i + 1, len(lines)
        cap, label = self.label(m.group(1), ('tab',), ln)
        j, rows = i + 1, []
        while j < n and lines[j].strip().startswith('|'):
            rows.append((j + 1, lines[j].strip()))
            j += 1
        if not rows:
            self.p.error(self.where(ln), '"Table:" caption must be followed directly by a pipe '
                                         'table (no blank line between)')
            return i + 1
        if len(rows) < 3:
            self.p.error(self.where(ln), 'a table needs a header row, the |---| separator and '
                                         'at least one row')
            return j
        header = split_row(rows[0][1])
        if not SEPARATOR_RE.match(rows[1][1]):
            self.p.error(self.where(rows[1][0]), 'the second table line must be the |---|---| '
                                                 'separator')
            return j
        seps = split_row(rows[1][1])
        aligns = ['center' if c.startswith(':') and c.endswith(':') else
                  'right' if c.endswith(':') else 'left' for c in seps]
        if len(aligns) != len(header):
            self.p.error(self.where(rows[1][0]), f'separator has {len(aligns)} columns, header '
                                                 f'has {len(header)}')
            aligns = (aligns + ['left'] * len(header))[:len(header)]
        body = []
        for rln, r in rows[2:]:
            cells = split_row(r)
            if len(cells) != len(header):
                self.p.error(self.where(rln), f'row has {len(cells)} cells, header has '
                                              f'{len(header)} (escape a literal pipe as \\|)')
                cells = (cells + [''] * len(header))[:len(header)]
            body.append((rln, cells))
        if len(header) > MAX_TABLE_COLS:
            self.p.gap(self.where(ln), f'table has {len(header)} columns (limit '
                                       f'{MAX_TABLE_COLS})')
        self.u.blocks.append(dict(t='table', line=ln, caption=cap, label=label, header=header,
                                  header_line=rows[0][0], rows=body, aligns=aligns))
        return j

    def figure(self, s, ln):
        m = FIGURE_RE.match(s)
        if not m:
            self.p.error(self.where(ln), 'malformed figure line - expected '
                                         '![Caption](docs/figures/report/x.png){#fig:label width=15cm}')
            return
        label, width = None, None
        for tok in (m.group('attrs') or '{}')[1:-1].split():
            if tok.startswith('#'):
                _, label = self.label('{' + tok + '}', ('fig',), ln)
            elif re.match(r'^width=\d+(\.\d+)?(cm|mm)$', tok):
                v = float(re.findall(r'[\d.]+', tok)[0])
                width = v / 10 if tok.endswith('mm') else v
            else:
                self.p.error(self.where(ln), f'unknown figure attribute {tok!r} (allowed: '
                                             '#fig:label, width=NNcm)')
        if width is not None and width > MAX_FIG_W:
            self.p.gap(self.where(ln), f'figure width {width:g} cm exceeds {MAX_FIG_W:g} cm')
            width = MAX_FIG_W
        self.u.blocks.append(dict(t='figure', line=ln, caption=m.group('cap').strip(),
                                  path=m.group('path'), label=label, width=width))

    def equation(self, s, ln):
        m = EQUATION_RE.match(s)
        if not m:
            self.p.error(self.where(ln), 'malformed equation - expected "$$ math $$ {#eq:label}" '
                                         'on one line')
            return
        label = None
        if m.group('attrs'):
            _, label = self.label(m.group('attrs'), ('eq',), ln)
        self.u.blocks.append(dict(t='equation', line=ln, body=m.group('body'), label=label))

    def list_block(self, lines, i):
        n, items = len(lines), []
        while i < n:
            mm = LIST_RE.match(lines[i].rstrip())
            if not mm:
                break
            indent = len(mm.group('indent'))
            if indent not in (0, 2):
                self.p.error(self.where(i + 1), 'list items are indented by 0 or 2 spaces '
                                                '(one nesting level)')
            level = 0 if indent == 0 else 1
            if level == 1 and not items:
                self.p.error(self.where(i + 1), 'nested list item without a parent item')
            marker = mm.group('marker')
            items.append(dict(level=level, ordered=marker != '-', line=i + 1,
                              start=int(marker[:-1]) if marker != '-' else None,
                              text=mm.group('text').strip()))
            i += 1
        if i < n and lines[i].strip() and not is_block_start(lines[i]):
            self.p.error(self.where(i + 1), 'a list item continues on the next line - items are '
                                            'never hard-wrapped (join the lines)')
            while i < n and lines[i].strip() and not is_block_start(lines[i]):
                i += 1
        self.u.blocks.append(dict(t='list', line=items[0]['line'], items=items))
        return i

    def paragraph(self, lines, i):
        ln, n = i + 1, len(lines)
        text = lines[i].strip()
        j = i + 1
        if j < n and lines[j].strip() and not is_block_start(lines[j]):
            self.p.error(self.where(j + 1), 'the paragraph continues on this line - paragraphs '
                                            'are never hard-wrapped (join the lines, or put a '
                                            'blank line between paragraphs)')
            while j < n and lines[j].strip() and not is_block_start(lines[j]):
                text += ' ' + lines[j].strip()
                j += 1
        self.u.blocks.append(dict(t='para', line=ln, text=text))
        return j


def inline_texts(block):
    """(line, text) of every inline-formatted string of a block, in reading order."""
    t = block['t']
    if t in ('h2', 'h3', 'h4', 'para'):
        yield block['line'], block['text']
    elif t == 'list':
        for it in block['items']:
            yield it['line'], it['text']
    elif t == 'table':
        yield block['line'], block['caption']
        for c in block['header']:
            yield block['header_line'], c
        for rln, cells in block['rows']:
            for c in cells:
                yield rln, c
    elif t in ('figure', 'code'):
        yield block['line'], block['caption']


def parse_ref_items(token):
    """'[@cite:a; @cite:b]' -> [('cite', 'a'), ('cite', 'b')], or None if malformed."""
    items = []
    for part in token[1:-1].split(';'):
        m = REF_ITEM_RE.match(part)
        if not m:
            return None
        items.append((m.group(1), m.group(2)))
    return items


# =========================================================================== numbering pass
def number_units(units, probs):
    """Number sections, figures, tables, equations and code blocks chapter-wise and
    register every label -> (display text, where)."""
    labels = {}

    def register(label, display, where):
        if not label:
            return
        if label in labels:
            probs.error(where, f'duplicate label {{#{label}}} (first used at {labels[label][1]})')
        else:
            labels[label] = (display, where)

    for u in units:
        if u.kind == 'front' or not u.present:
            continue
        register(u.title_label, u.display, f'{u.fname}:1')
        c = dict(sec=0, sub=0, fig=0, tab=0, eq=0, alg=0, lst=0)
        for b in u.blocks:
            where, t = f'{u.fname}:{b["line"]}', b['t']
            if t == 'h2':
                c['sec'], c['sub'] = c['sec'] + 1, 0
                b['num'] = f'{u.num}.{c["sec"]}'
                register(b['label'], f'Section {b["num"]}', where)
            elif t == 'h3':
                if c['sec'] == 0:
                    probs.error(where, '### subsection before the first ## section')
                c['sub'] += 1
                b['num'] = f'{u.num}.{c["sec"]}.{c["sub"]}'
                register(b['label'], f'Section {b["num"]}', where)
            elif t in ('figure', 'table', 'equation'):
                key = {'figure': 'fig', 'table': 'tab', 'equation': 'eq'}[t]
                c[key] += 1
                b['num'] = f'{u.num}.{c[key]}'
                shown = {'figure': f'Figure {b["num"]}', 'table': f'Table {b["num"]}',
                         'equation': f'Equation ({b["num"]})'}[t]
                register(b['label'], shown, where)
            elif t == 'code':
                c[b['kind']] += 1
                b['num'] = f'{u.num}.{c[b["kind"]]}'
                word = 'Algorithm' if b['kind'] == 'alg' else 'Listing'
                register(b['label'], f'{word} {b["num"]}', where)
    return labels


def number_citations(units, refs, probs):
    """IEEE numbering: order of first citation across chapters 1-9 and the appendices."""
    order = {}
    for u in units:
        if not u.present:
            continue
        for b in u.blocks:
            for ln, text in inline_texts(b):
                for m in re.finditer(r'\[@[^\[\]]*\]', text):
                    items = parse_ref_items(m.group(0)) or []
                    for kind, key in items:
                        if kind != 'cite':
                            continue
                        if u.kind == 'front':
                            probs.error(f'{u.fname}:{ln}', 'citations are not allowed in front '
                                                           'matter')
                        elif key in refs and key not in order:
                            order[key] = len(order) + 1
    return order


# =========================================================================== docx helpers
PPR_ORDER = ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl',
             'numPr', 'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens',
             'kinsoku', 'wordWrap', 'overflowPunct', 'topLinePunct', 'autoSpaceDE',
             'autoSpaceDN', 'bidi', 'adjustRightInd', 'snapToGrid', 'spacing', 'ind',
             'contextualSpacing', 'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection',
             'textAlignment', 'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr',
             'sectPr', 'pPrChange']


def ppr_set(pPr, el):
    """Insert (or replace) a w:pPr child at its schema position - Word rejects files whose
    property elements are out of order."""
    name = el.tag.split('}')[1]
    old = pPr.find(qn('w:' + name))
    if old is not None:
        pPr.remove(old)
    later = PPR_ORDER[PPR_ORDER.index(name) + 1:]
    pPr.insert_element_before(el, *['w:' + t for t in later])


def border_el(tag, sides, sz=4, color=BORDER_GREY, space=4):
    el = OxmlElement(tag)
    for side in ('top', 'left', 'bottom', 'right'):
        if side in sides:
            s = OxmlElement('w:' + side)
            s.set(qn('w:val'), 'single')
            s.set(qn('w:sz'), str(sz))
            s.set(qn('w:space'), str(space))
            s.set(qn('w:color'), color)
            el.append(s)
    return el


def shd_el(fill):
    el = OxmlElement('w:shd')
    el.set(qn('w:val'), 'clear')
    el.set(qn('w:color'), 'auto')
    el.set(qn('w:fill'), fill)
    return el


def set_fonts(rPr, name):
    """Set all four font slots and drop theme-font references (which would win)."""
    rf = rPr.get_or_add_rFonts()
    for a in ('w:asciiTheme', 'w:hAnsiTheme', 'w:eastAsiaTheme', 'w:cstheme'):
        rf.attrib.pop(qn(a), None)
    for a in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rf.set(qn(a), name)


# Prose typography (never applied to code): no line break inside 'ρ = 0.317', '684 ms'
# or 'FR-24' - a no-break space (U+00A0) around a spaced operator and between a number
# and its unit, a no-break hyphen (U+2011, present in Times New Roman) inside an
# upper-case identifier.
NOBREAK_OP_RE = re.compile(r' ([=±≤≥<>≈×]) ')
NOBREAK_UNIT_RE = re.compile(r'(?<=\d) (?=(?:ms|s|min|h|kB|MB|GB|Hz|kHz|dB|cm|mm)\b)')
NOBREAK_ID_RE = re.compile(r'(?<!\w)([A-Z][A-Z0-9]{0,5})-(?=[A-Z0-9])')
# A hyphen that signs a number ('-0.0100', '[-0.0167, ...]', not '18-24' or 'FR-24')
# prints as a minus sign (U+2212): Word may break a line after a hyphen, which split
# '[-' from '0.0167' in narrow table cells, but never after a minus sign.
MINUS_RE = re.compile(r'(?<![\w.)\]\-])-(?=\d)')


def typeset(text, prev=''):
    """Curly quotes from straight ones (opening after a space, an opening bracket or a
    dash, closing otherwise; 'prev' is the character already printed before 'text'),
    then the no-break rules and the minus sign above."""
    before = prev[-1:]
    out = []
    for ch in text:
        if ch in '"\'':
            opening = not prev or prev.isspace() or prev in '([{—–-/“‘'
            ch = ('“' if opening else '”') if ch == '"' else ('‘' if opening else '’')
        out.append(ch)
        prev = ch
    s = NOBREAK_OP_RE.sub('\u00a0\\1\u00a0', ''.join(out))
    s = NOBREAK_UNIT_RE.sub('\u00a0', s)
    s = MINUS_RE.sub('\u2212', before + s)[len(before):]
    return NOBREAK_ID_RE.sub('\\1\u2011', s)


def fmt_run(r, font=None, size=None, bold=None, italic=None, color=None, highlight=False,
            superscript=None, subscript=None):
    if font:
        set_fonts(r._r.get_or_add_rPr(), font)
    if size:
        r.font.size = Pt(size)
    if bold is not None:
        r.font.bold = bold
    if italic is not None:
        r.font.italic = italic
    if color is not None:
        r.font.color.rgb = color
    if highlight:
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    if superscript:
        r.font.superscript = True
    if subscript:
        r.font.subscript = True
    return r


def add_field(par, instr, placeholder='', **run_fmt):
    """Insert a Word field: begin / instrText / separate / placeholder result / end."""
    def fld_run(child):
        r = fmt_run(par.add_run(), **run_fmt)
        r._r.append(child)

    for kind, text in (('begin', None), ('instr', instr), ('separate', None)):
        if kind == 'instr':
            el = OxmlElement('w:instrText')
            el.set(qn('xml:space'), 'preserve')
            el.text = f' {text} '
        else:
            el = OxmlElement('w:fldChar')
            el.set(qn('w:fldCharType'), kind)
        fld_run(el)
    if placeholder:
        fmt_run(par.add_run(placeholder), **run_fmt)
    el = OxmlElement('w:fldChar')
    el.set(qn('w:fldCharType'), 'end')
    fld_run(el)


def pformat(p, align=None, before=None, after=None, line=None, keep_next=None, left=None,
            first=None, page_break=None):
    pf = p.paragraph_format
    if align is not None:
        p.alignment = align
    if before is not None:
        pf.space_before = Pt(before)
    if after is not None:
        pf.space_after = Pt(after)
    if line is not None:
        pf.line_spacing = line
    if keep_next is not None:
        pf.keep_with_next = keep_next
    if left is not None:
        pf.left_indent = Cm(left)
    if first is not None:
        pf.first_line_indent = Cm(first)
    if page_break is not None:
        pf.page_break_before = page_break
    return p


# =========================================================================== styles
def style_conf(st, font=BODY_FONT, size=BODY_PT, bold=False, italic=False, align=None,
               before=0, after=0, line=1.0, keep_next=False, left=None, first=None, tabs=()):
    set_fonts(st.element.get_or_add_rPr(), font)
    st.font.size = Pt(size)
    st.font.bold = bold
    st.font.italic = italic
    st.font.color.rgb = BLACK
    pf = st.paragraph_format
    if align is not None:
        pf.alignment = align
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.line_spacing = line
    pf.keep_with_next = keep_next
    pf.widow_control = True
    if left is not None:
        pf.left_indent = Cm(left)
    if first is not None:
        pf.first_line_indent = Cm(first)
    old = st.element.get_or_add_pPr().find(qn('w:tabs'))
    if old is not None:                       # drop inherited template tab stops
        old.getparent().remove(old)
    for pos, kind, leader in tabs:
        pf.tab_stops.add_tab_stop(Cm(pos), kind, leader)
    return st


def para_style(doc, name, base='Normal', style_id=None, **conf):
    """Get or create a paragraph style. style_id lets built-in styles keep Word's id
    ('TOC1' for 'toc 1'), which python-docx would otherwise derive differently."""
    try:
        st = doc.styles[name]
    except KeyError:
        if style_id:
            el = OxmlElement('w:style')
            el.set(qn('w:type'), 'paragraph')
            el.set(qn('w:styleId'), style_id)
            for tag, val in (('w:name', name), ('w:basedOn', 'Normal'), ('w:uiPriority', '39')):
                sub = OxmlElement(tag)
                sub.set(qn('w:val'), val)
                el.append(sub)
            doc.styles.element.append(el)
            st = doc.styles[name]
        else:
            st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            st.base_style = doc.styles[base]
            st.quick_style = True
    return style_conf(st, **conf)


def setup_styles(doc):
    J, C, L = WD_ALIGN_PARAGRAPH.JUSTIFY, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT
    TL, TC_, TR = WD_TAB_ALIGNMENT.LEFT, WD_TAB_ALIGNMENT.CENTER, WD_TAB_ALIGNMENT.RIGHT
    NO, DOTS = WD_TAB_LEADER.SPACES, WD_TAB_LEADER.DOTS

    # document defaults: no theme fonts, no template spacing
    defaults = doc.styles.element.find(qn('w:docDefaults'))
    set_fonts(defaults.find(qn('w:rPrDefault')).find(qn('w:rPr')), BODY_FONT)
    ppr_default = defaults.find(qn('w:pPrDefault'))
    if ppr_default is not None:
        defaults.remove(ppr_default)

    # body text: 12 pt Times New Roman, 1.5 spacing, justified
    style_conf(doc.styles['Normal'], size=BODY_PT, align=J, after=6, line=1.5)
    # headings drive the table of contents (levels 1-3) and the PDF bookmarks
    style_conf(doc.styles['Heading 1'], size=H1_PT, bold=True, align=C, after=24, line=1.5,
               keep_next=True)
    style_conf(doc.styles['Heading 2'], size=H2_PT, bold=True, align=L, before=18, after=6,
               line=1.15, keep_next=True)
    style_conf(doc.styles['Heading 3'], size=H3_PT, bold=True, align=L, before=12, after=6,
               line=1.15, keep_next=True)
    style_conf(doc.styles['Heading 4'], size=H4_PT, bold=True, align=L, before=10, after=4,
               line=1.15, keep_next=True)

    para_style(doc, 'Front Heading', size=16, bold=True, align=C, before=12, after=24,
               keep_next=True)
    para_style(doc, 'Figure', align=C, before=6, after=2, keep_next=True)
    para_style(doc, 'Figure Caption', size=CAPTION_PT, align=C, before=2, after=12)
    para_style(doc, 'Table Caption', size=CAPTION_PT, align=C, before=10, after=4,
               keep_next=True)
    para_style(doc, 'Code Caption', size=CAPTION_PT, align=C, before=10, after=4,
               keep_next=True)
    code = para_style(doc, 'Code', font=CODE_FONT, size=CODE_PT, align=L, left=0.15)
    code.paragraph_format.right_indent = Cm(0.15)
    ppr = code.element.get_or_add_pPr()
    ppr_set(ppr, border_el('w:pBdr', ('top', 'left', 'bottom', 'right')))
    ppr_set(ppr, shd_el(CODE_FILL))
    para_style(doc, 'Equation', align=L, before=6, after=6, line=1.15,
               tabs=[(TEXT_W / 2, TC_, NO), (TEXT_W, TR, NO)])
    para_style(doc, 'Table Text', size=TABLE_PT, align=L, before=2, after=2)
    para_style(doc, 'Table Header', size=TABLE_PT, bold=True, align=C, before=2, after=2,
               keep_next=True)
    para_style(doc, 'Spacer', size=6, align=L)
    para_style(doc, 'Reference', align=L, after=6, line=1.15, left=1.1, first=-1.1,
               tabs=[(1.1, TL, NO)])
    para_style(doc, 'List Item 1', align=J, after=3, line=1.5, left=1.0, first=-0.5,
               tabs=[(1.0, TL, NO)])
    para_style(doc, 'List Item 2', align=J, after=3, line=1.5, left=1.6, first=-0.5,
               tabs=[(1.6, TL, NO)])
    para_style(doc, 'Front Text', align=J, after=8, line=1.5)
    para_style(doc, 'TOC Header', bold=True, align=L, after=8,
               tabs=[(TEXT_W / 2, TC_, NO), (TEXT_W, TR, NO)])
    # TOC entry styles. Level 1 = chapters, References, appendices (bold, template-like
    # number column - see finalize_report.py), 2-3 = sections, 4 = figure/table lists.
    # The right indent keeps long titles out of the page-number column; the dotted
    # right tab sits beyond it, at the margin.
    para_style(doc, 'toc 1', style_id='TOC1', bold=True, align=L, before=6, after=0,
               left=2.4, first=-2.4, tabs=[(1.2, TC_, NO), (2.4, TL, NO), (TEXT_W, TR, DOTS)])
    para_style(doc, 'toc 2', style_id='TOC2', align=L, before=2, left=4.2, first=-1.0,
               tabs=[(TEXT_W, TR, DOTS)])
    para_style(doc, 'toc 3', style_id='TOC3', align=L, before=0, left=5.6, first=-1.2,
               tabs=[(TEXT_W, TR, DOTS)])
    para_style(doc, 'toc 4', style_id='TOC4', align=L, before=3, left=2.6, first=-2.6,
               tabs=[(TEXT_W, TR, DOTS)])
    for k in range(1, 5):
        doc.styles[f'toc {k}'].paragraph_format.right_indent = Cm(1.0)
    for name in ('Header', 'Footer'):
        style_conf(doc.styles[name], size=10, align=L)
    # TOC entries are hyperlinks; keep them black and not underlined
    try:
        hl = doc.styles['Hyperlink']
    except KeyError:
        hl = doc.styles.add_style('Hyperlink', WD_STYLE_TYPE.CHARACTER)
    hl.font.color.rgb = BLACK
    hl.font.underline = False


# =========================================================================== rendering
class Renderer:
    def __init__(self, doc, probs, preview, labels, cites, refs, units, src):
        self.doc, self.p, self.preview = doc, probs, preview
        self.pending = PENDING if preview else None
        self.labels, self.cites, self.refs = labels, cites, refs
        self.units = {u.prefix: u for u in units if u.kind != 'front'}
        self.src = src
        self.unit = None

    # ---------------------------------------------------------------- inline text
    def where(self, ln):
        return f'{self.unit.fname}:{ln}'

    def fill(self, s, where):
        try:
            return PN.fill(s, pending=self.pending)
        except (KeyError, ValueError) as e:
            msg = e.args[0] if e.args else str(e)
            self.p.error(where, f'{msg} (numbers are {{key}} placeholders from '
                                'tools/project_numbers.py; braces are not allowed otherwise)')
            return s

    def fill_code(self, s, where):
        """Code is verbatim except {key} placeholders of registered numbers, so real code
        braces ({}, f'{x:.3f}', Kotlin blocks) pass through untouched."""
        def rep(m):
            k = m.group(1)
            if k in PN.NUM:
                return PN.NUM[k]
            if k in getattr(PN, '_HINT', {}):
                if self.pending:
                    return self.pending
                self.p.gap(where, f'{{{k}}} is not available yet (from {PN._HINT[k]})')
            return m.group(0)
        return re.sub(r'\{(\w+)\}', rep, s)

    def check_text(self, s, where):
        checks = [
            ('`' in s, 'unbalanced backtick'),
            ('[@' in s, 'malformed reference - write [@kind:label] or [@cite:key; @cite:key2]'),
            (re.search(r'</?[A-Za-z][A-Za-z0-9]*(\s[^<>]*)?/?>', s), 'raw HTML is not allowed'),
            (re.search(r'\\[A-Za-z]+', s), 'LaTeX commands are not allowed'),
            (re.search(r'\[[^\]]+\]\([^)]+\)', s), 'Markdown links are not supported - write '
                                                   'the address as plain text or cite it'),
            ('![' in s, 'figures go on their own line'),
            ('$$' in s, 'display equations go on their own line'),
            (re.search(r'(?<![\w/.])[A-Za-z]_[A-Za-z0-9](?![\w(])', s),
             'x_i prints literally in prose - write x~i~ (subscript) or x^2^ (superscript); '
             '_ and ^ act only inside $$ equations'),
            ('~' in s or '^' in s, 'stray ~ or ^ - prose sub/superscripts are H~t~ and x^2^ '
                                   '(1-12 characters, no spaces)'),
            (re.search('[\U0001F000-\U0001FAFF\u2B50\u2B55]', s), 'emojis are not allowed'),
        ]
        for bad, msg in checks:
            if bad:
                self.p.error(where, f'{msg}: {s.strip()[:60]!r}')

    def check_superseded(self, s, where):
        m = SUPERSEDED_RE.search(s)
        if m:
            self.p.gap(where, f'superseded survey number "{m.group(0)}" - quote only the '
                              'final-sample keys from tools/project_numbers.py')

    def add_text(self, par, text, highlight=False, **f):
        """Prose run(s); code never comes through here, so typeset() is safe."""
        runs = par.runs
        text = typeset(text, runs[-1].text[-1:] if runs and runs[-1].text else '')
        for piece in (re.split(r'(\[pending\])', text) if self.pending else [text]):
            if piece:
                fmt_run(par.add_run(piece), highlight=highlight or piece == PENDING, **f)

    def ref_text(self, token, where):
        """[@...] -> ('Table 6.1', True) or a visible marker and False."""
        items = parse_ref_items(token)
        if items is None:
            self.p.error(where, f'malformed reference {token} - write [@kind:label] or '
                                '[@cite:key1; @cite:key2]')
            return token, False
        kinds = {k for k, _ in items}
        if 'cite' in kinds and len(kinds) > 1:
            self.p.error(where, f'{token} mixes citations and cross-references')
            return token, False
        ok, out = True, []
        if kinds == {'cite'}:
            for _, key in items:
                if key in self.cites:
                    out.append(f'[{self.cites[key]}]')
                else:
                    ok = False
                    out.append(f'[?{key}]')
                    self.p.gap(where, f'unknown citation key "{key}" - not in references.json '
                                      'or any references_extra_*.json')
            return ', '.join(out), ok
        for kind, key in items:
            label = f'{kind}:{key}'
            if label in self.labels:
                out.append(self.labels[label][0])
                continue
            ok = False
            out.append(f'[?{label}]')
            m = re.match(r'(ch[1-9]|app[a-z])-', key)
            target = self.units.get(m.group(1)) if m else None
            if target is not None and not target.present:
                self.p.gap(where, f'{token} points into {target.display} ({target.fname}), '
                                  'which is not written yet')
            else:
                self.p.gap(where, f'unknown cross-reference label {token}')
        return (out[0] if len(out) == 1 else ', '.join(out[:-1]) + ' and ' + out[-1]), ok

    def inline(self, par, text, ln, size=None, code_size=INLINE_CODE_PT, bold=False,
               italic=False):
        """Render **bold**, *italic*, `code`, [@refs], {numbers} and the prose
        sub/superscripts H~t~ and x^2^ (Pandoc syntax) into runs."""
        where = self.where(ln)
        tb = ti = False
        for seg in re.split(r'(`[^`]*`|\*\*|\*|\[@[^\[\]]*\]|~[^~\s]{1,12}~|\^[^\^\s]{1,12}\^)',
                            text):
            if not seg:
                continue
            if seg == '**':
                tb = not tb
            elif seg == '*':
                ti = not ti
            elif len(seg) >= 3 and seg[0] == seg[-1] and seg[0] in '~^':
                self.add_text(par, self.fill(seg[1:-1], where), size=size,
                              bold=bold or tb or None, italic=italic or ti or None,
                              subscript=seg[0] == '~', superscript=seg[0] == '^')
            elif len(seg) >= 2 and seg[0] == '`' and seg[-1] == '`':
                fmt_run(par.add_run(self.fill_code(seg[1:-1], where)), font=CODE_FONT,
                        size=code_size, bold=bold or tb or None, italic=italic or ti or None)
            elif seg.startswith('[@'):
                txt, ok = self.ref_text(seg, where)
                self.add_text(par, txt, highlight=not ok, size=size, bold=bold or tb or None,
                              italic=italic or ti or None)
            else:
                self.check_text(seg, where)
                filled = self.fill(seg, where)
                self.check_superseded(filled, where)
                self.add_text(par, filled, size=size, bold=bold or tb or None,
                              italic=italic or ti or None)
        if tb or ti:
            self.p.error(where, 'unbalanced ** or * (bold and italic markers come in pairs)')

    def plain(self, text, ln):
        """Filled text without markup - for word counts and width estimates."""
        s = re.sub(r'\[@[^\[\]]*\]', '[00]', text)
        s = s.replace('**', '').replace('*', '').replace('`', '')
        s = re.sub(r'([~^])([^~^\s]{1,12})\1', r'\2', s)
        try:
            return PN.fill(s, pending=PENDING) if '{' in s else s
        except (KeyError, ValueError):
            return re.sub(r'\{\w+\}', '00000', s)

    # ---------------------------------------------------------------- blocks
    def chapter_heading(self, label, title, page_break=False):
        p = self.doc.add_paragraph(style='Heading 1')
        if label:
            p.add_run(label)
            p.add_run().add_break()
        p.add_run(title.upper())
        if page_break:
            p.paragraph_format.page_break_before = True
        return p

    def render_unit(self, u):
        self.unit = u
        label = CHAPTER_LABEL.format(n=u.num) if u.kind == 'chapter' else f'APPENDIX {u.num}'
        self.chapter_heading(label, u.title)
        for b in u.blocks:
            getattr(self, 'r_' + b['t'])(b)

    def r_h2(self, b):
        self._heading(b, 'Heading 2')

    def r_h3(self, b):
        self._heading(b, 'Heading 3')

    def r_h4(self, b):
        self._heading(b, 'Heading 4')

    def _heading(self, b, style):
        p = self.doc.add_paragraph(style=style)
        if b.get('num'):
            p.add_run(b['num'] + ' ')
        self.inline(p, b['text'], b['line'], code_size=None)

    def r_para(self, b):
        p = self.doc.add_paragraph()
        self.inline(p, b['text'], b['line'])

    def r_list(self, b):
        counters = {}
        for k, it in enumerate(b['items']):
            lvl = it['level']
            for deeper in [x for x in counters if x > lvl]:
                del counters[deeper]
            if it['ordered']:
                counters[lvl] = counters[lvl] + 1 if lvl in counters else it['start']
                marker = f'{counters[lvl]}.'
            else:
                counters.pop(lvl, None)
                marker = '•' if lvl == 0 else '–'
            p = self.doc.add_paragraph(style='List Item 1' if lvl == 0 else 'List Item 2')
            p.add_run(marker + '\t')
            self.inline(p, it['text'], it['line'])
            if k == len(b['items']) - 1:
                p.paragraph_format.space_after = Pt(8)

    def caption(self, style, word, b):
        p = self.doc.add_paragraph(style=style)
        fmt_run(p.add_run(f'{word} {b["num"]}:'), bold=True)
        p.add_run(' ')
        self.inline(p, b['caption'], b['line'], code_size=CAPTION_PT - 1)
        return p

    def spacer(self):
        self.doc.add_paragraph(style='Spacer')

    def r_table(self, b):
        self.caption('Table Caption', 'Table', b)
        header, rows, aligns = b['header'], b['rows'], b['aligns']
        ncol = len(header)
        t = self.doc.add_table(rows=1 + len(rows), cols=ncol)
        t.style = self.doc.styles['Table Grid']
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        widths = self.column_widths(b)
        tblW = t._tbl.tblPr.find(qn('w:tblW'))
        if tblW is not None:
            tblW.set(qn('w:type'), 'dxa')
            tblW.set(qn('w:w'), str(int(sum(widths) / 2.54 * 1440)))
        for c, w in enumerate(widths):
            t.columns[c].width = Cm(w)
        amap = {'left': WD_ALIGN_PARAGRAPH.LEFT, 'center': WD_ALIGN_PARAGRAPH.CENTER,
                'right': WD_ALIGN_PARAGRAPH.RIGHT}
        keep = (len(rows) <= KEEP_TABLE_TOGETHER_ROWS
                and self.table_height(b, widths) <= KEEP_TABLE_MAX_CM)
        all_rows = [(b['header_line'], header)] + rows
        # a table that may split still keeps its header with two rows, and its last two
        # rows together, so neither page holds a lone header or a lone row
        glue = set(range(len(all_rows) - 1)) if keep else {0, 1, len(all_rows) - 2}
        for r, (ln, cells) in enumerate(all_rows):
            row = t.rows[r]
            trPr = row._tr.get_or_add_trPr()
            trPr.append(OxmlElement('w:cantSplit'))
            if r == 0:
                trPr.append(OxmlElement('w:tblHeader'))      # repeat on every page
            for c, text in enumerate(cells):
                cell = row.cells[c]
                cell.width = Cm(widths[c])
                par = cell.paragraphs[0]
                par.style = self.doc.styles['Table Header' if r == 0 else 'Table Text']
                if r == 0:
                    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    cell._tc.get_or_add_tcPr().insert_element_before(
                        shd_el(GREY_FILL), 'w:noWrap', 'w:tcMar', 'w:textDirection',
                        'w:tcFitText', 'w:vAlign', 'w:hideMark')
                else:
                    par.alignment = amap[aligns[c]]
                if r in glue and r < len(all_rows) - 1:
                    par.paragraph_format.keep_with_next = True
                self.inline(par, text, ln, size=None, code_size=TABLE_CODE_PT)
        self.spacer()

    def table_height(self, b, widths):
        """Rough rendered height in cm: lines per cell from the text length at 10.5 pt
        (0.19 cm a character, 0.20 for code) over the column width, 0.43 cm a line."""
        def text_cm(cell):
            total = 0.0
            for part in re.split(r'(`[^`]*`)', cell):
                if len(part) >= 2 and part[0] == part[-1] == '`':
                    total += (len(part) - 2) * 0.20
                elif part:
                    total += len(self.plain(part, b['line'])) * 0.19
            return total
        h = 0.9                                             # caption and spacing
        for cells in [b['header']] + [c for _, c in b['rows']]:
            lines = max(max(1, -(-1.1 * text_cm(t) // max(w - 0.4, 0.5)))
                        for t, w in zip(cells, widths))
            h += lines * 0.43 + 0.16
        return h

    def column_widths(self, b):
        """Share the text width between columns from their content: every column gets
        at least its longest unbreakable piece (a word, or a whole `code` span such as an
        endpoint path), the rest goes to the columns with longer text."""
        per_char, code_char, pad = 0.19, 0.20, 0.4     # cm at 10.5 pt / 9.5 pt code; margins

        def word_w(word):
            # an unbreakable piece must fit whole: capitals are wider than the average
            # letter, so 'NFR-17' gets the 1.3 cm it needs instead of wrapping at its hyphen
            return sum(0.26 if ch.isupper() else 0.19 if ch.isdigit() else
                       0.13 if ch in ".,;:-'()/|" else per_char for ch in word)

        def measure(cell, factor):
            total = longest = 0.0
            for part in re.split(r'(`[^`]*`)', cell):
                if len(part) >= 2 and part[0] == part[-1] == '`':
                    w = (len(part) - 2) * code_char
                    total, longest = total + w, max(longest, w)
                elif part:
                    txt = self.plain(part, b['line'])
                    total += len(txt) * per_char * factor
                    longest = max([longest] + [word_w(x) * factor for x in txt.split()])
            return total, min(longest, 0.45 * TEXT_W)

        want, need = [], []
        for c in range(len(b['header'])):
            sizes = [measure(b['header'][c], 1.08)] + [measure(cells[c], 1.0)
                                                       for _, cells in b['rows']]
            want.append(max(s[0] for s in sizes) + pad)
            need.append(max(s[1] for s in sizes) + pad)
        total = TEXT_W
        if sum(want) <= total:
            return [w * total / sum(want) for w in want]
        if sum(need) >= total:
            return [w * total / sum(need) for w in need]
        spare, extra = total - sum(need), [w - n for w, n in zip(want, need)]
        return [n + spare * e / sum(extra) for n, e in zip(need, extra)]

    def r_figure(self, b):
        path = b['path']
        cands = [path] if os.path.isabs(path) else [os.path.join(ROOT, path),
                                                    os.path.join(self.src, path)]
        found = next((c for c in cands if os.path.isfile(c)), None)
        p = self.doc.add_paragraph(style='Figure')
        if not found:
            self.p.gap(self.where(b['line']), f'figure file not found: {path}')
            self.add_text(p, f'[missing figure: {path}]', highlight=True)
        else:
            pic = p.add_run().add_picture(found, width=Cm(b['width'] or DEFAULT_FIG_W))
            if pic.height > Cm(MAX_FIG_H):                   # never taller than a page allows
                pic.width = int(pic.width * Cm(MAX_FIG_H) / pic.height)
                pic.height = Cm(MAX_FIG_H)
        self.caption('Figure Caption', 'Figure', b)

    def r_equation(self, b):
        p = self.doc.add_paragraph(style='Equation')
        p.add_run('\t')
        body = self.fill(b['body'], self.where(b['line']))
        self.check_superseded(body, self.where(b['line']))
        # x_i, x_(a b) -> subscript; x^2, x^(n+1) -> superscript
        pos = 0
        for m in re.finditer(r'([_^])(\([^()]*\)|[^\W_]+)', body):
            if m.start() > pos:
                p.add_run(body[pos:m.start()])
            inner = m.group(2)[1:-1] if m.group(2).startswith('(') else m.group(2)
            fmt_run(p.add_run(inner), subscript=m.group(1) == '_',
                    superscript=m.group(1) == '^')
            pos = m.end()
        if pos < len(body):
            p.add_run(body[pos:])
        p.add_run(f'\t({b["num"]})')

    def r_code(self, b):
        self.caption('Code Caption', 'Algorithm' if b['kind'] == 'alg' else 'Listing', b)
        lines = b['lines']
        for k, line in enumerate(lines):
            p = self.doc.add_paragraph(style='Code')
            if line:
                p.add_run(self.fill_code(line, self.where(b['line'] + 2 + k)))
            if k < len(lines) - 1:
                p.paragraph_format.keep_with_next = True
        self.spacer()


# =========================================================================== page furniture
def new_section(doc):
    """Start a new section on a new page. python-docx holds the previous section's
    properties in an empty paragraph; shrink it to 1 pt so that it can never spill onto
    a blank page of its own."""
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    brk = doc.paragraphs[-1]
    pf = brk.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing = Pt(1)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    rpr = OxmlElement('w:rPr')
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '2')
    rpr.append(sz)
    ppr_set(brk._p.get_or_add_pPr(), rpr)
    return sec


def page_setup(sec):
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.left_margin = sec.right_margin = Cm(MARGIN)
    sec.top_margin = sec.bottom_margin = Cm(MARGIN)
    sec.header_distance, sec.footer_distance = Cm(HEADER_DIST), Cm(FOOTER_DIST)
    sec.gutter = Cm(0)


def page_numbering(sec, fmt, start=None):
    """w:pgNumType: number format and (optionally) restart value of a section."""
    sectPr = sec._sectPr
    old = sectPr.find(qn('w:pgNumType'))
    if old is not None:
        sectPr.remove(old)
    el = OxmlElement('w:pgNumType')
    el.set(qn('w:fmt'), fmt)
    if start is not None:
        el.set(qn('w:start'), str(start))
    sectPr.insert_element_before(el, 'w:cols', 'w:formProt', 'w:vAlign', 'w:noEndnote',
                                 'w:titlePg', 'w:textDirection', 'w:bidi', 'w:rtlGutter',
                                 'w:docGrid', 'w:printerSettings', 'w:sectPrChange')


def running_header(hdr):
    """Project title left, PES logo right, rule below (body pages from Chapter 1)."""
    p = hdr.paragraphs[0]
    p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W), WD_TAB_ALIGNMENT.RIGHT)
    fmt_run(p.add_run(PROJECT_TITLE), font=BODY_FONT, size=10)
    p.add_run('\t')
    p.add_run().add_picture(LOGO, height=Cm(LOGO_HEADER_H))
    ppr_set(p._p.get_or_add_pPr(), border_el('w:pBdr', ('bottom',), sz=6, color='000000',
                                             space=4))


def running_footer(ftr):
    """Rule above; "Dept. of CSE" left, period centre, page number right."""
    p = ftr.paragraphs[0]
    pf = p.paragraph_format
    pf.tab_stops.add_tab_stop(Cm(TEXT_W / 2), WD_TAB_ALIGNMENT.CENTER)
    pf.tab_stops.add_tab_stop(Cm(TEXT_W), WD_TAB_ALIGNMENT.RIGHT)
    fmt_run(p.add_run('Dept. of CSE\t' + FOOTER_PERIOD + '\t'), font=BODY_FONT, size=10)
    add_field(p, 'PAGE', '1', font=BODY_FONT, size=10)
    ppr_set(p._p.get_or_add_pPr(), border_el('w:pBdr', ('top',), sz=6, color='000000',
                                             space=4))


def body_section_furniture(sec, first):
    """Chapters, References and appendices: no header on a chapter's first page, the
    footer on every page. The first body section defines the header/footer; the later
    ones inherit them (linked to previous) and only switch on 'different first page'."""
    sec.different_first_page_header_footer = True
    if first:
        page_numbering(sec, 'decimal', 1)
        sec.header.is_linked_to_previous = False
        running_header(sec.header)
        sec.first_page_header.is_linked_to_previous = False      # empty
        for ftr in (sec.footer, sec.first_page_footer):
            ftr.is_linked_to_previous = False
            running_footer(ftr)
    else:
        page_numbering(sec, 'decimal')


# =========================================================================== front matter
def tline(doc, runs, size, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0, font=TITLE_FONT,
          line=1.0, **f):
    """One centred line of a template page; runs = str or [(text, {overrides})]."""
    p = pformat(doc.add_paragraph(), align=align, before=before, after=after, line=line)
    for text, over in ([(runs, {})] if isinstance(runs, str) else runs):
        kw = dict(font=font, size=size)
        kw.update(f)
        kw.update(over)
        fmt_run(p.add_run(text), **kw)
    return p


def borderless_table(doc, rows, widths, cell_fn):
    t = doc.add_table(rows=rows, cols=len(widths))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for c, w in enumerate(widths):
        t.columns[c].width = Cm(w)
    for r in range(rows):
        for c, w in enumerate(widths):
            cell = t.rows[r].cells[c]
            cell.width = Cm(w)
            cell_fn(r, c, cell)
    return t


def cell_line(cell, text, size, font=TITLE_FONT, first=False, align=WD_ALIGN_PARAGRAPH.CENTER,
              **f):
    p = cell.paragraphs[0] if first else cell.add_paragraph()
    pformat(p, align=align, before=0, after=0, line=1.0)
    if text:
        fmt_run(p.add_run(text), font=font, size=size, **f)
    return p


def designation_run(p, font, size, prefix=''):
    if prefix:
        fmt_run(p.add_run(prefix), font=font, size=size)
    fmt_run(p.add_run(GUIDE_DESIGNATION or 'Designation'), font=font, size=size,
            highlight=GUIDE_DESIGNATION is None)


def logo(doc, width_cm, before=0):
    p = pformat(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.CENTER, before=before, after=0,
                line=1.0)
    p.add_run().add_picture(LOGO, width=Cm(width_cm))
    return p


def names_table(doc, size):
    def fill(r, c, cell):
        cell_line(cell, TEAM[r][c], size, first=True, bold=True)
    borderless_table(doc, len(TEAM), [5.6, 5.6], fill)


def title_page(doc):
    """Inner title page - wording and layout of p01-02_title_certificate.docx (page 1)."""
    logo(doc, 4.3, before=6)
    tline(doc, 'Dissertation on', 16, before=14, bold=True, italic=True)
    tline(doc, f'“{PROJECT_TITLE}”', 16, before=10, bold=True, color=RGBColor(0x00, 0x6F, 0xBF))
    tline(doc, 'Submitted in partial fulfilment of the requirements for the award of degree of',
          12.5, before=8, italic=True)
    tline(doc, 'Bachelor of Technology', 16, before=20, bold=True)
    tline(doc, 'in', 16, bold=True)
    tline(doc, 'Computer Science & Engineering', 16, bold=True)
    tline(doc, [(COURSE, {'size': 14.5}), (' – Capstone Project Phase - 3', {})], 16, before=16,
          bold=True)
    tline(doc, 'Submitted by:', 12, before=26, after=6, bold=True, italic=True)
    names_table(doc, 14)
    tline(doc, 'Under the guidance of', 12, before=18, after=6, italic=True)
    tline(doc, GUIDE, 14, font=BODY_FONT, bold=True)
    p = tline(doc, '', 14, font=BODY_FONT)
    designation_run(p, BODY_FONT, 14)
    tline(doc, 'PES University', 14, font=BODY_FONT)
    tline(doc, PERIOD, 12, before=16, bold=True, color=RGBColor(0xBF, 0x4F, 0x4C))
    tline(doc, 'DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING', 12, before=36, bold=True)
    tline(doc, 'FACULTY OF ENGINEERING', 12)
    tline(doc, 'PES UNIVERSITY', 12, bold=True)
    tline(doc, '(Established under Karnataka Act No. 16 of 2013)', 10, before=2)
    tline(doc, '100ft Ring Road, Bengaluru – 560 085, Karnataka, India', 10)


def certificate_page(doc):
    """Certificate - wording and layout of p01-02_title_certificate.docx (page 2)."""
    logo(doc, 3.9).paragraph_format.page_break_before = True
    tline(doc, '(Established under Karnataka Act No. 16 of 2013)', 8, before=2)
    tline(doc, '100ft Ring Road, Bengaluru – 560 085, Karnataka, India', 10)
    tline(doc, 'FACULTY OF ENGINEERING', 12, before=14, bold=True)
    tline(doc, 'CERTIFICATE', 20, before=22, bold=True)
    tline(doc, 'This is to certify that the dissertation entitled', 12, before=14, italic=True)
    tline(doc, f'‘{PROJECT_TITLE}’', 14, before=14, bold=True)
    tline(doc, 'is a bonafide work carried out by', 11, before=14, after=8, italic=True)
    names_table(doc, 12)
    p = tline(doc, [('in partial fulfilment for the completion of seventh semester Capstone '
                     f'Project Phase - 3 ({COURSE}) in the Program of Study - Bachelor of '
                     'Technology in Computer Science and Engineering under rules and '
                     'regulations of PES University, Bengaluru during the period '
                     f'{PERIOD}. It is certified that all corrections / suggestions indicated '
                     'for internal assessment have been incorporated in the report. The '
                     'dissertation has been approved as it satisfies the 7', {}),
                    ('th', {'superscript': True}),
                    (' semester academic requirements in respect of project work.', {})],
              10, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=14, after=30, line=1.5)
    p.paragraph_format.left_indent = p.paragraph_format.right_indent = Cm(0.4)

    signers = [(GUIDE, None, True), ('Dr. Shylaja S S', 'Chairperson', False),
               ('Dr. Sridhar K S', 'Registrar', False)]

    def sig(r, c, cell):
        name, role, bold = signers[c]
        cell_line(cell, 'Signature', 10, first=True)
        cell_line(cell, name, 10, bold=bold)
        if role:
            cell_line(cell, role, 10)
        else:
            designation_run(cell_line(cell, '', 10), TITLE_FONT, 10)
    borderless_table(doc, 1, [5.6, 5.6, 5.6], sig)

    tline(doc, 'External Viva', 10, before=40, after=10, bold=True)
    rule = '__________________________'

    def viva(r, c, cell):
        left = WD_ALIGN_PARAGRAPH.LEFT if c == 0 else WD_ALIGN_PARAGRAPH.CENTER
        cell_line(cell, 'Name of the Examiners' if c == 0 else 'Signature with Date', 10,
                  first=True, align=left, bold=True)
        for k in (1, 2):
            cell_line(cell, '', 10)
            p = cell_line(cell, '', 10, align=left)
            if c == 0:
                fmt_run(p.add_run(f'{k}. '), font=TITLE_FONT, size=10, bold=True)
            fmt_run(p.add_run(rule), font=TITLE_FONT, size=10)
    borderless_table(doc, 1, [8.3, 8.3], viva)


def declaration_page(doc):
    """Declaration - wording of p03-08_declaration_ack_abstract_toc.docx (page 1)."""
    pformat(doc.add_paragraph('DECLARATION', style='Front Heading'), before=24, after=36)
    p = pformat(doc.add_paragraph(style='Front Text'), line=1.5, after=24)
    parts = [('We hereby declare that the Capstone Project Phase - 3 entitled ', False),
             (f'“{PROJECT_TITLE}”', True),
             (f' has been carried out by us under the guidance of {GUIDE}, ', False)]
    for text, bold in parts:
        fmt_run(p.add_run(text), size=14, bold=bold or None)
    designation_run(p, BODY_FONT, 14)
    parts = [(' and submitted in partial fulfilment of the course requirements for the award '
              'of degree of ', False), ('Bachelor of Technology', True), (' in ', False),
             ('Computer Science and Engineering', True), (' of ', False),
             ('PES University, Bengaluru', True),
             (f' during the academic semester {PERIOD}. The matter embodied in this report has '
              'not been submitted to any other university or institution for the award of any '
              'degree.', False)]
    for text, bold in parts:
        fmt_run(p.add_run(text), size=14, bold=bold or None)

    def fill(r, c, cell):
        name, srn = TEAM[r]
        text = [srn, name, ''][c]
        p = cell_line(cell, text, 12, font=BODY_FONT, first=True, bold=True,
                      align=WD_ALIGN_PARAGRAPH.LEFT)
        pformat(p, before=6, after=6)
    borderless_table(doc, len(TEAM), [4.6, 5.4, 4.4], fill)


def front_text_page(doc, r, unit, probs, heading):
    """Acknowledgement / abstract from their Markdown files."""
    pformat(doc.add_paragraph(heading, style='Front Heading'), page_break=True, before=24)
    r.unit = unit
    words = 0
    for b in unit.blocks:
        if b['t'] != 'para':
            probs.error(f'{unit.fname}:{b["line"]}', 'front matter holds plain paragraphs only')
            continue
        p = doc.add_paragraph(style='Front Text')
        text = b['text']
        m = re.match(r'^\*{0,2}(Keywords?)\s*:\s*\*{0,2}\s*(.*)$', text)
        if unit.fname == '00_abstract.md' and m:
            pformat(p, before=6, align=WD_ALIGN_PARAGRAPH.LEFT)
            fmt_run(p.add_run(m.group(1) + ': '), bold=True, italic=True)
            r.inline(p, m.group(2), b['line'])
            continue
        r.inline(p, text, b['line'])
        words += len(r.plain(text, b['line']).split())
    if unit.fname == '00_abstract.md' and words > ABSTRACT_MAX_WORDS:
        probs.error(unit.fname, f'abstract has {words} words (limit {ABSTRACT_MAX_WORDS}, '
                                'Keywords line excluded)')
    return words


def toc_page(doc, heading, columns, instr, page_break=True):
    pformat(doc.add_paragraph(heading, style='Front Heading'), page_break=page_break, before=24)
    p = doc.add_paragraph(style='TOC Header')
    for k, col in enumerate(columns):
        p.add_run(('\t' if k else '') + col)
    add_field(doc.add_paragraph(), instr, 'Right-click and choose Update Field, or run '
                                          'python tools/finalize_report.py')


# =========================================================================== main build
def load_units(src, preview, probs):
    units = [Unit('front', '', f) for _, f in FRONT]
    units += [Unit('chapter', n, f) for n, f in CHAPTERS]
    units += [Unit('appendix', n, f) for n, f in APPENDICES]
    for u in units:
        path = os.path.join(src, u.fname)
        if not os.path.exists(path):
            msg = f'{u.fname} is missing (not written yet) - skipped'
            (probs.gap if preview else probs.error)('', msg)
            continue
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()
        u.present = True
        Parser(u, probs).parse(text)
    return units


def ensure_logo():
    if not os.path.exists(LOGO):
        os.makedirs(FIG_DIR, exist_ok=True)
        with zipfile.ZipFile(LOGO_SOURCE[0]) as z, open(LOGO, 'wb') as f:
            f.write(z.read(LOGO_SOURCE[1]))


def build(src, out, preview):
    probs = Problems()
    ensure_logo()
    refs = load_refs(src, probs)
    units = load_units(src, preview, probs)
    labels = number_units(units, probs)
    cites = number_citations(units, refs, probs)

    doc = Document()
    setup_styles(doc)
    view = OxmlElement('w:view')                   # open in Print Layout, not Web Layout
    view.set(qn('w:val'), 'print')
    settings = doc.settings.element
    old = settings.find(qn('w:view'))
    if old is not None:
        settings.remove(old)
    wp = settings.find(qn('w:writeProtection'))
    settings.insert(list(settings).index(wp) + 1 if wp is not None else 0, view)
    cp = doc.core_properties
    cp.title, cp.subject = PROJECT_TITLE, f'{COURSE} Capstone Project Phase-3 report'
    cp.author = ', '.join(n for n, _ in TEAM)
    cp.comments = 'Built by tools/build_report_docx.py from docs/report/*.md'
    r = Renderer(doc, probs, preview, labels, cites, refs, units, src)

    # -- section A: title page and certificate (no page numbers)
    page_setup(doc.sections[0])
    title_page(doc)
    certificate_page(doc)

    # -- section B: declaration .. list of tables, numbered i, ii, iii (footer centre)
    sec = new_section(doc)
    page_numbering(sec, 'lowerRoman', 1)
    sec.different_first_page_header_footer = False
    sec.header.is_linked_to_previous = False
    sec.footer.is_linked_to_previous = False
    fp = pformat(sec.footer.paragraphs[0], align=WD_ALIGN_PARAGRAPH.CENTER)
    add_field(fp, 'PAGE', 'i', font=BODY_FONT, size=11)
    declaration_page(doc)
    front = {u.fname: u for u in units if u.kind == 'front'}
    abstract_words = 0
    for fname, heading in (('00_acknowledgement.md', 'ACKNOWLEDGEMENT'),
                           ('00_abstract.md', 'ABSTRACT')):
        u = front[fname]
        if u.present:
            words = front_text_page(doc, r, u, probs, u.title.upper() or heading)
            if fname == '00_abstract.md':
                abstract_words = words
    toc_page(doc, 'TABLE OF CONTENTS', ['Chapter No.', 'Title', 'Page No.'],
             r'TOC \o "1-3" \h \z \u')
    toc_page(doc, 'LIST OF FIGURES', ['Figure No.', 'Title', 'Page No.'],
             r'TOC \h \z \t "Figure Caption,4"')
    toc_page(doc, 'LIST OF TABLES', ['Table No.', 'Title', 'Page No.'],
             r'TOC \h \z \t "Table Caption,4"')

    # -- body: one section per chapter, the references and each appendix
    first = True
    body = [u for u in units if u.kind != 'front' and u.present]
    for u in [x for x in body if x.kind == 'chapter']:
        body_section_furniture(new_section(doc), first)
        first = False
        r.render_unit(u)
    body_section_furniture(new_section(doc), first)
    first = False
    r.chapter_heading(None, 'REFERENCES')
    for key, n in sorted(cites.items(), key=lambda kv: kv[1]):
        p = doc.add_paragraph(style='Reference')
        p.add_run(f'[{n}]\t' + refs[key])
    if not cites:
        probs.gap('', 'no citations found - the References section is empty')
    for u in [x for x in body if x.kind == 'appendix']:
        body_section_furniture(new_section(doc), first)
        r.render_unit(u)

    if GUIDE_DESIGNATION is None:
        probs.note('FILL-IN: the guide\'s designation is not recorded in the repository - '
                   'the title page, certificate and declaration print a yellow "Designation". '
                   'Set GUIDE_DESIGNATION in tools/build_report_docx.py.')
    stats = dict(units=sum(1 for u in body), refs=len(cites), uncited=len(refs) - len(cites),
                 abstract_words=abstract_words,
                 figures=sum(1 for u in body for b in u.blocks if b['t'] == 'figure'),
                 tables=sum(1 for u in body for b in u.blocks if b['t'] == 'table'))
    return doc, probs, stats


def main():
    ap = argparse.ArgumentParser(description='Build the department-format Word report from '
                                             'docs/report/*.md.')
    ap.add_argument('--preview', action='store_true',
                    help='draft build: missing chapters, citations, labels, figures and '
                         'not-yet-available numbers become highlighted markers')
    ap.add_argument('--src', default=REPORT_SRC, help='folder with the chapter sources '
                                                      '(default docs/report)')
    ap.add_argument('--out', default=OUT_DOCX, help='output .docx (default '
                                                    'docs/CAPSTONE_REPORT.docx)')
    ap.add_argument('--refresh-refs', action='store_true',
                    help='rebuild docs/report/references.json from the .tex bibliographies')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    if a.refresh_refs:
        refresh_refs(os.path.join(REPORT_SRC, 'references.json'))
        return 0
    src = os.path.abspath(a.src)
    doc, probs, stats = build(src, a.out, a.preview)

    for n in probs.notes:
        print('NOTE   ', n)
    if probs.gaps:
        head = 'WARNING' if a.preview else 'ERROR  '
        print(f'\n{len(probs.gaps)} gap(s)' + (' - errors in a final build:' if a.preview
                                               else ':'))
        for g in probs.gaps:
            print(head, g)
    if probs.errors:
        print(f'\n{len(probs.errors)} error(s):')
        for e in probs.errors:
            print('ERROR  ', e)
    if probs.errors or (probs.gaps and not a.preview):
        print('\nbuild FAILED - nothing written')
        return 1
    try:
        doc.save(a.out)
    except PermissionError:
        print(f'\ncannot write {a.out} - is it open in Word? Close it and run again.')
        return 1
    print(f'\nwrote {os.path.relpath(a.out, ROOT)} ({"preview" if a.preview else "final"}): '
          f'{stats["units"]} chapters/appendices, {stats["figures"]} figures, '
          f'{stats["tables"]} tables, {stats["refs"]} references cited '
          f'({stats["uncited"]} uncited not printed), abstract {stats["abstract_words"]}/'
          f'{ABSTRACT_MAX_WORDS} words')
    print('next: python tools/finalize_report.py   (Word fills the TOC and page numbers, '
          'writes the PDF)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
