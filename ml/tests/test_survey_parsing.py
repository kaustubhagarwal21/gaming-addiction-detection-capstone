# -*- coding: utf-8 -*-
"""Guard the survey form <-> analysis-script contract.

Why this exists: ml/eval_behavior_survey.py locates columns by KEYWORD in the
Google Forms header text. A single reworded question therefore silently breaks
parsing — and the failure surfaces only AFTER responses are collected, when the
data cannot be gathered again. This test builds a CSV with the exact headers the
documented form produces and asserts the pipeline actually keeps the rows.

It caught a real defect before launch: 'do you play video games' matched the
hours-per-week question, binding the yes/no eligibility gate to a banded answer
and dropping 120/120 responses.

Run: python -m pytest ml/tests/test_survey_parsing.py -q
"""
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURE = os.path.join(HERE, '_form_fixture.py')
CSV_PATH = os.path.join(HERE, 'sim_responses.csv')


def _build_fixture():
    subprocess.run([sys.executable, '-X', 'utf8', FIXTURE], check=True,
                   capture_output=True)
    assert os.path.exists(CSV_PATH)
    return CSV_PATH


def test_documented_form_headers_parse_and_keep_rows():
    """The documented form's export must yield usable rows, not silent drops."""
    path = _build_fixture()
    out = subprocess.run(
        [sys.executable, '-X', 'utf8',
         os.path.join(ROOT, 'ml', 'eval_behavior_survey.py'), path],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    combined = (out.stdout or '') + (out.stderr or '')
    assert 'No usable responses' not in combined, (
        'Every simulated response was dropped — the form wording and the '
        'analysis keywords have drifted apart:\n' + combined[:800])
    # 120 simulated rows, all eligible and passing the attention check
    assert '120 raw -> 120 usable' in combined or '-> 120 usable' in combined, (
        'Unexpected drop count:\n' + combined[:800])


def test_every_required_column_is_findable():
    """Each keyword the script needs must match exactly one documented header."""
    sys.path.insert(0, os.path.join(ROOT, 'ml'))
    from eval_behavior_survey import find_col, IGDS_KEYS

    with open(_build_fixture(), encoding='utf-8') as f:
        headers = next(csv.reader(f))

    required = ['18', 'currently play video games', 'hours per week', 'typical day',
                'days per week', 'after midnight', 'longer than 3 hours',
                'within 15 minutes', 'consecutive days', 'quality control']
    for kw in required:
        assert find_col(headers, kw) is not None, f'no header matches {kw!r}'
    assert find_col(headers, 'single', 'session') is not None
    for kw in IGDS_KEYS:
        assert find_col(headers, kw) is not None, f'IGDS item {kw!r} not found'


def test_eligibility_gate_is_a_yes_no_column():
    """Regression: the gate must not bind to a banded (non-yes/no) answer."""
    sys.path.insert(0, os.path.join(ROOT, 'ml'))
    from eval_behavior_survey import find_col

    with open(_build_fixture(), encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        first = next(reader)
    gate = find_col(headers, 'currently play video games')
    assert str(first[gate]).strip().lower() in ('yes', 'no'), (
        f'eligibility gate bound to {gate!r} whose value is {first[gate]!r} — '
        'it must be the Yes/No question')
