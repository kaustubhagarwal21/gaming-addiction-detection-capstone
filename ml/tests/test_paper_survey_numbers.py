# -*- coding: utf-8 -*-
"""Guard the survey-results <-> written-documents contract.

Why this exists: the IGDS9-SF study's numbers are quoted by hand in four places
(the paper, the defense notes, the validation plan, the slide outline). Every
re-run of ml/eval_behavior_survey.py or ml/eval_survey_extras.py can shift a
figure -- a wider bootstrap, one more response, a model retrain -- and a stale
number in the paper is a defect an examiner finds before we do. This test asserts
that what the documents claim is what the committed aggregate JSON actually says.

It also pins the two scripts to agreeing with each other on the ONE quantity they
both compute (the headline correlation and its CI). They previously disagreed in
the third decimal because they bootstrapped at different resample counts, which
would have put two different confidence intervals for the same statistic into the
same repository.

Run: python -m pytest ml/tests/test_paper_survey_numbers.py -q
"""
import io
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOCS = os.path.join(ROOT, 'docs')

VALIDATION = os.path.join(DOCS, 'survey_validation.json')
EXTRAS = os.path.join(DOCS, 'survey_extras.json')

pytestmark = pytest.mark.skipif(
    not (os.path.exists(VALIDATION) and os.path.exists(EXTRAS)),
    reason='survey aggregates not present (study not run in this checkout)')


def _read(name):
    with io.open(os.path.join(DOCS, name), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def agg():
    with io.open(VALIDATION, encoding='utf-8') as f:
        v = json.load(f)
    with io.open(EXTRAS, encoding='utf-8') as f:
        x = json.load(f)
    return v, x


def test_scripts_agree_on_the_headline(agg):
    """Both scripts compute the construct-validity rho; they must not disagree."""
    v, x = agg
    assert round(v['construct_validity']['rho'], 3) == round(x['incremental']['rho_model'], 3)
    for a, b in zip(v['construct_validity']['ci95'], x['incremental']['rho_model_ci']):
        assert round(a, 3) == round(b, 3), 'the two scripts report different CIs'


def test_sample_sizes_are_consistent(agg):
    v, x = agg
    assert v['n_raw'] == x['n_raw']
    # scoreable <= usable: a respondent can pass eligibility yet skip a pattern question
    assert x['n'] <= v['n_usable'] <= v['n_raw']
    assert sum(v['dropped'].values()) == v['n_raw'] - v['n_usable']


def test_documents_quote_the_committed_numbers(agg):
    """Every headline figure must appear verbatim in the documents that cite it."""
    v, x = agg
    inc, comps = x['incremental'], x['features']['composites']
    rho, (lo, hi) = v['construct_validity']['rho'], v['construct_validity']['ci95']

    headline = [f'{rho:.3f}', f'{lo:.3f}, {hi:.3f}', f'{inc["rho_hours"]:.3f}',
                f'{inc["delta_rho"]:.3f}', f'{inc["partial_rho"]:.3f}',
                f'{comps["pattern"]["rho"]:.3f}', f'{comps["volume"]["rho"]:.3f}',
                f'{x["genre"]["p"]:.3f}']
    for doc in ('PROJECT_PAPER.tex', 'DEFENSE_NOTES.md', 'VALIDATION_PLAN.md'):
        text = _read(doc)
        missing = [n for n in headline if n not in text]
        assert not missing, f'{doc} is missing / has stale: {missing}'


def test_caseness_metrics_stay_withheld(agg):
    """The honesty guard: no sensitivity/specificity while positives are in single digits."""
    v, _ = agg
    if v['caseness_auc'].get('withheld'):
        assert v['caseness_auc']['positives'] < 10
        for doc in ('PROJECT_PAPER.tex', 'DEFENSE_NOTES.md'):
            text = _read(doc).lower()
            # the documents must say so rather than quietly omitting it
            assert 'caseness' in text, f'{doc} does not disclose the withheld metrics'
