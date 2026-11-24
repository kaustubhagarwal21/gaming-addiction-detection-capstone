# -*- coding: utf-8 -*-
"""Finish the Word report: update every field and table of contents, save, export a PDF.

    python tools/finalize_report.py                       # docs/CAPSTONE_REPORT.docx -> .pdf
    python tools/finalize_report.py --docx X.docx --pdf X.pdf

python-docx (tools/build_report_docx.py) can write fields - TOC, PAGE - but cannot
compute them: page numbers only exist once a layout engine has paginated the text.
This script drives Microsoft Word 16 through COM (pywin32) to do that:

  1. start a private, invisible Word instance (DispatchEx, so a Word window the user
     already has open is never touched) with every dialog suppressed;
  2. open the .docx, update all fields in every story (body, headers, footers), then
     update every table of contents - the main TOC and the two TOC fields that build
     the List of Figures / List of Tables - twice, because filling the TOC can push
     later pages down and change the very numbers it lists;
  3. save the .docx in place and export the PDF;
  4. close the document and quit Word in a finally block, and as a last resort kill
     any WINWORD.EXE process that this script started and that is still running.

Windows only. The .docx must not be open in Word while this runs (Word would refuse to
save over a file that it has locked).
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DOCX = os.path.join(ROOT, 'docs', 'CAPSTONE_REPORT.docx')

# Word constants (from the Word object model; named here instead of importing the
# generated type library, which needs makepy and is not always present).
WD_ALERTS_NONE = 0
WD_DO_NOT_SAVE_CHANGES = 0
WD_EXPORT_FORMAT_PDF = 17
WD_EXPORT_OPTIMIZE_FOR_PRINT = 0
WD_EXPORT_ALL_DOCUMENT = 0
WD_EXPORT_DOCUMENT_CONTENT = 0
WD_EXPORT_CREATE_HEADING_BOOKMARKS = 1
MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3
WD_NUMBER_OF_PAGES_IN_DOCUMENT = 4
WD_FIND_STOP = 0
WD_REPLACE_ONE = 1
WD_PRINT_VIEW = 3


def word_pids():
    """PIDs of all running WINWORD.EXE processes (empty set if none)."""
    try:
        out = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq WINWORD.EXE', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower().startswith('winword') and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def update_all_fields(doc):
    """Update the fields of every story: main text, headers, footers, text boxes."""
    for story in doc.StoryRanges:
        rng = story
        while rng is not None:
            rng.Fields.Update()
            try:
                rng = rng.NextStoryRange
            except Exception:
                rng = None


def tidy_toc_chapter_numbers(doc):
    """Department template look for the main table of contents: Word builds a chapter
    entry from its two-line heading as 'CHAPTER 3 LITERATURE REVIEW'; this turns it into
    '<tab>3.<tab>LITERATURE REVIEW' so the number sits in the 'Chapter No.' column (the
    'toc 1' style of build_report_docx.py has the matching tab stops). It runs after the
    last update; a later manual 'Update Field' in Word just restores the plain form."""
    if doc.TablesOfContents.Count == 0:
        return 0
    done = 0
    for k in range(1, 21):
        for label in (f'CHAPTER {k} ', f'CHAPTER-{k} '):
            find = doc.TablesOfContents(1).Range.Find
            find.ClearFormatting()
            find.Replacement.ClearFormatting()
            if find.Execute(FindText=label, MatchCase=True, MatchWholeWord=False,
                            MatchWildcards=False, MatchSoundsLike=False,
                            MatchAllWordForms=False, Forward=True, Wrap=WD_FIND_STOP,
                            Format=False, ReplaceWith=f'^t{k}.^t', Replace=WD_REPLACE_ONE):
                done += 1
    return done


def finalize(docx_path, pdf_path, passes=2, tidy_toc=True):
    import pythoncom
    import win32com.client

    docx_path = os.path.abspath(docx_path)
    pdf_path = os.path.abspath(pdf_path)
    if not os.path.exists(docx_path):
        sys.exit(f'finalize_report: {docx_path} not found - run tools/build_report_docx.py first')

    before = word_pids()
    pythoncom.CoInitialize()
    word = doc = None
    try:
        word = win32com.client.DispatchEx('Word.Application')
        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        # NB: do not set word.ScreenUpdating = False - Word 16 then drops paragraph
        # borders (header/footer rules, code boxes) from the exported PDF.
        try:
            word.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE  # no macros
        except Exception:
            pass

        doc = word.Documents.Open(FileName=docx_path, ConfirmConversions=False,
                                  ReadOnly=False, AddToRecentFiles=False, Visible=False)
        try:   # paginate (and save) in Print Layout, never Web Layout
            doc.Windows(1).View.Type = WD_PRINT_VIEW
        except Exception:
            pass
        n_toc = doc.TablesOfContents.Count
        for k in range(passes):
            update_all_fields(doc)
            for i in range(1, doc.TablesOfContents.Count + 1):
                doc.TablesOfContents(i).Update()
            doc.Repaginate()
            pages = doc.Content.Information(WD_NUMBER_OF_PAGES_IN_DOCUMENT)
            print(f'finalize_report: pass {k + 1}/{passes} - fields and {n_toc} tables of '
                  f'contents updated, {pages} pages')
        if tidy_toc:
            tidy_toc_chapter_numbers(doc)
        doc.Save()
        doc.ExportAsFixedFormat(
            OutputFileName=pdf_path, ExportFormat=WD_EXPORT_FORMAT_PDF,
            OpenAfterExport=False, OptimizeFor=WD_EXPORT_OPTIMIZE_FOR_PRINT,
            Range=WD_EXPORT_ALL_DOCUMENT, Item=WD_EXPORT_DOCUMENT_CONTENT,
            IncludeDocProps=True, KeepIRM=True,
            CreateBookmarks=WD_EXPORT_CREATE_HEADING_BOOKMARKS,
            DocStructureTags=True, BitmapMissingFonts=True, UseISO19005_1=False)
        print(f'finalize_report: saved {os.path.relpath(docx_path, ROOT)} and wrote '
              f'{os.path.relpath(pdf_path, ROOT)}')
    finally:
        if doc is not None:
            try:
                doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
            except Exception:
                pass
        doc = word = None
        pythoncom.CoUninitialize()
        # Safety net: never leave a Word process behind. Only processes that did not
        # exist before this script started are touched, so the user's own Word stays.
        for _ in range(20):
            leftover = word_pids() - before
            if not leftover:
                break
            time.sleep(0.5)
        else:
            for pid in leftover:
                subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
                print(f'finalize_report: killed leftover WINWORD.EXE (pid {pid})')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--docx', default=DEFAULT_DOCX, help='report to finalise (updated in place)')
    ap.add_argument('--pdf', default=None, help='PDF to write (default: next to the .docx)')
    ap.add_argument('--passes', type=int, default=2, help='TOC update passes (default 2)')
    ap.add_argument('--plain-toc', action='store_true',
                    help='keep "CHAPTER n TITLE" entries (skip the Chapter No. column tidy)')
    a = ap.parse_args()
    pdf = a.pdf or os.path.splitext(a.docx)[0] + '.pdf'
    finalize(a.docx, pdf, a.passes, tidy_toc=not a.plain_toc)


if __name__ == '__main__':
    main()
