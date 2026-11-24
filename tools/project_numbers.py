# -*- coding: utf-8 -*-
"""One source of truth for every number the Review 3 deck and the project report quote.

Both builders (tools/build_pes_review3_deck.py, tools/build_report_docx.py) write
numbers into their text as {placeholders}; fill() replaces them from the committed
result JSONs in docs/. An unknown placeholder, or a stray brace left in the text, is
an error, never a silent pass, so slide/report text cannot drift from the data.

Optional sources (present only after the corresponding work has run):
  docs/genre_removal.json  - written when the genre weight left the served score
  docs/test_counts.json    - written by tools/count_tests.py
  docs/hparam_behaviour.json, docs/hparam_chat.json, docs/hparam_voice.json
                           - written by ml/hparam_behaviour.py, ml/hparam_chat.py,
                             ml/hparam_voice.py (hp_* keys; only if the study passed
                             its replication gate)
Keys from a missing optional source are simply absent, so text that uses them
fails loudly with a hint instead of printing a stale literal.

Run `python tools/project_numbers.py` to list every key and its current value.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')


def _load(name):
    with open(os.path.join(DOCS, name), encoding='utf-8') as f:
        return json.load(f)


def _opt(name):
    p = os.path.join(DOCS, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def _ci(v, signed=False, nd=3):
    fmt = '{:+.%df}' % nd if signed else '{:.%df}' % nd
    return '[' + fmt.format(v[0]) + ', ' + fmt.format(v[1]) + ']'


def _pct(x, nd=1):
    return f'{x * 100:.{nd}f}%'


def _latex_pages(name):
    log = os.path.join(DOCS, name + '.log')
    if os.path.exists(log):
        with open(log, encoding='utf-8', errors='ignore') as f:
            m = re.search(r'Output written on ' + re.escape(name) + r'\.pdf \((\d+) pages', f.read())
        if m:
            return m.group(1)
    return None


def _pdf_pages(path):
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as d:
            return str(d.page_count)
    except Exception:
        return None


PAPER_LITERALS = {
    # chat: deployed operating point on held-out real gaming chat (paper Table, sec. Results/chat)
    'chat_p_deployed': '0.956',          # precision @ alert threshold 0.95
    'chat_r_deployed': '0.428',          # recall @ 0.95  (ablation-protocol view is chat_r_alert_abl)
    # PR-AUC of the SERVED chat model on the same held-out gaming chat (backend/models/
    # model_metadata.json chat_metrics_gaming.pr_auc 0.8208). Quote it beside chat_p/r_deployed;
    # chat_prauc (0.825) is the recipe under the ablation protocol and pairs with chat_*_abl.
    'chat_prauc_served': '0.821',
    'toxic_bert': '0.709',               # Detoxify/toxic-BERT PR-AUC on the same gaming chat
    'hindi_p_deva': '0.968',             # Hindi Devanagari precision @ 0.95
    'hindi_p_roman': '0.958',            # Hindi romanised precision @ 0.95
    'hindi_heldout_rows': '933',
    # voice: deployed model, speaker-independent (ablation protocol reads voice_acc_abl)
    'voice_acc': '0.574',
    'voice_random_split': '0.657',
    'voice_leak_gap': '8.3',             # points, random split minus speaker-independent
    'voice_speakers': '154',
    'voice_corpora': '4',
    'voice_languages': '3',
    # behaviour model
    'beh_cv': '0.921 ± 0.002',           # 5-fold CV accuracy
    'beh_ece_before': '0.062',
    'beh_ece_after': '0.015',            # isotonic calibration
    # system / device (TESTING.md device drill 2026-08-18, Galaxy M52; load test)
    'load_requests': '288',
    'load_p50': '66 ms',
    'load_p95': '684 ms',
    # same load test re-run after score v2 (TESTING.md, 2026-11-23): 0 errors, max 819 ms
    'load_rerun_date': '23 November 2026',
    'load_rerun_p50': '64 ms',
    'load_rerun_p95': '607 ms',
    # live Render free instance, measured 2026-11-23 from Bengaluru (server, not the ChildApp)
    'live_warm': '211 ms',               # warm request round trip
    'live_cold_start': '39.6 s',         # first request after the free instance slept
    'cpu_default': '14%',                # of one core, default English-STT path
    'mem_default': '288–301 MB',
    'cpu_dual': '51–72%',                # dual Hindi+English STT (fails the gate -> default OFF)
    'mem_dual': '399–419 MB',
    'cold_start': '569 ms',
    'session_autostart': '~10 s',
    'session_autoend': '~25 s',
    'nudge_latency': '~12 s',
    # family pilot
    'pilot_days': '23',                  # 6–28 July 2026
}


def build():
    SV = _load('survey_validation.json')
    SX = _load('survey_extras.json')
    AB = _load('ablation_results.json')
    AF = _load('asr_fairness.json')
    FS = _load('fusion_sensitivity.json')
    VH = _load('voice_headroom.json')

    inc = SX['incremental']
    comp = SX['features']['composites']
    beh = {r['config']: r for r in AB['behaviour']}
    chat = {r['config']: r for r in AB['chat']}
    voice = {r['config']: r for r in AB['voice']}
    fam = AF['by_language_family']
    m = re.search(r'(\d+)\s+speakers', AF.get('dataset', ''))

    N = {
        # ---- external validation (IGDS9-SF survey; FINAL n=134 raw) ----
        'rho': f"{SV['construct_validity']['rho']:.3f}",
        'rho_ci': _ci(SV['construct_validity']['ci95']),
        'n_scored': str(SV['construct_validity']['n']),
        'n_usable': str(SV['n_usable']),
        'n_raw': str(SV['n_raw']),
        'rho_hours': f"{inc['rho_hours']:.3f}",            # paired, scoreable subset (canonical)
        'rho_hours_ci': _ci(inc['rho_hours_ci']),
        'rho_hours_all': f"{SV['hours_vs_igds']['rho']:.3f}",  # all usable rows (eval_behavior_survey.py)
        'delta': f"{inc['delta_rho']:+.3f}",
        'delta_ci': _ci(inc['delta_ci'], signed=True),
        'p_model_better': _pct(inc['p_model_better']),
        'partial': f"{inc['partial_rho']:.3f}",
        'partial_ci': _ci(inc['partial_ci']),
        'pattern': f"{comp['pattern']['rho']:.3f}",
        'pattern_ci': _ci(comp['pattern']['ci']),
        'volume': f"{comp['volume']['rho']:.3f}",
        'volume_ci': _ci(comp['volume']['ci']),
        'contrast': f"{comp['pattern_minus_volume']['diff']:+.3f}",
        'contrast_ci': _ci(comp['pattern_minus_volume']['ci'], signed=True),
        'p_pattern_better': _pct(comp['pattern_minus_volume']['p_pattern_better']),
        'chat_premise': f"{SX['chat_premise']['rho']:.3f}",
        'genre_H': f"{SX['genre']['H']:.2f}",
        'genre_p': f"{SX['genre']['p']:.3f}",
        'genre_groups': str(SX['genre']['n_groups']),
        'genre_power': f"{SX['genre']['power_curve'][str(SX['n'])] * 100:.0f}%",
        'robust_rho': f"{SX['robustness']['excluding straight-line']['rho']:.3f}",
        'robust_n': str(SX['robustness']['excluding straight-line']['n']),
        'craving': f"{SX['proxies']['craving_score']:.3f}",
        'prevalence_k': str(SV['prevalence_36']['k']),
        't2_refit': f"{SV['threshold_fit']['RISK_T2']:.2f}",
        'kappa': f"{SV['threshold_fit']['kappa']:.3f}",

        # ---- behaviour model ablations (synthetic-label held-out set) ----
        'beh_acc': _pct(beh['objective-10 (deployed)']['accuracy']),
        'beh_acc_ci': _ci(beh['objective-10 (deployed)']['acc_ci95']),
        'beh_f1': f"{beh['objective-10 (deployed)']['macro_f1']:.3f}",
        'beh_screen_only': _pct(beh['screen-time only (hours, the baseline)']['accuracy']),
        'beh_pattern_only': _pct(beh['pattern features only (5)']['accuracy']),
        'beh_volume_only': _pct(beh['volume features only (5)']['accuracy']),
        'beh_all20': _pct(beh['all-20 (incl. derived proxies)']['accuracy']),

        # ---- chat model ablations (CONDA_valid, never trained on) ----
        'chat_prauc': f"{chat['full recipe (deployed)']['pr_auc']:.3f}",
        'chat_prauc_ci': _ci(chat['full recipe (deployed)']['pr_auc_ci95']),
        'chat_roc': f"{chat['full recipe (deployed)']['roc_auc']:.3f}",
        'no_conda': f"{chat['- CONDA corpus (domain data)']['pr_auc']:.3f}",
        'no_keyword': f"{chat['- keyword fusion']['pr_auc']:.3f}",
        'no_charwb': f"{chat['- char_wb n-grams']['pr_auc']:.3f}",
        'no_davidson': f"{chat['- Davidson corpus']['pr_auc']:.3f}",
        'chat_original': f"{chat['original (general-only, word-only)']['pr_auc']:.3f}",
        'chat_p_alert_abl': f"{chat['full recipe (deployed)']['precision@alert']:.3f}",
        'chat_r_alert_abl': f"{chat['full recipe (deployed)']['recall@alert']:.3f}",
        'alert_threshold': f"{AB['alert_threshold']:.2f}",

        # ---- voice model (speaker-independent) ----
        'voice_acc_abl': f"{voice['full (36 feats, 4 corpora, aug x1)']['accuracy']:.3f}",
        'voice_17feat': f"{voice['17-feature prefix']['accuracy']:.3f}",
        'voice_english_only': f"{voice['English-only training corpora']['accuracy']:.3f}",
        'voice_emb': f"{VH['B_emb_4class']['acc']:.3f}",

        # ---- ASR accent fairness (Svarah) ----
        'clips': f"{AF['overall']['clips']:,}",
        'speech_hours': f"{AF['overall']['speech_hours']:.1f}",
        'speakers': m.group(1) if m else '117',
        'wer_overall': _pct(AF['overall']['wer']),
        'wer_drav': _pct(fam['Dravidian']['wer']),
        'wer_ia': _pct(fam['Indo-Aryan']['wer']),
        'wer_tb': _pct(fam['Tibeto-Burman']['wer']),
        'false_alerts': str(AF['overall']['alerts_hyp']),

        # ---- fusion sensitivity on the production pilot (replication-gated) ----
        'pilot_sessions': str(FS['n']),
        'genre_band_shift': _pct(FS['genre_sweep']['x0.0']),
        'weight_flip_median': _pct(FS['weight_sweep']['median_band_flip']),
        'weight_flip_max': _pct(FS['weight_sweep']['max_band_flip']),
        'threshold_flip_max': _pct(max(FS['threshold_sweep'].values())),
        'beh_only_agree': _pct(FS['channel_contribution']['behaviour_only']['band_agreement']),
    }

    # ---- measured values that live in the audited report (docs/PROJECT_PAPER.tex),
    # not in a committed JSON. One place, with the section they come from, so the
    # deck and the Word report cannot quote two different versions of them.
    N.update(PAPER_LITERALS)

    ieee = _latex_pages('IEEE_PAPER')
    if ieee:
        N['ieee_pp'] = ieee
    for pdf in ('CAPSTONE_REPORT.pdf',):
        pp = _pdf_pages(os.path.join(DOCS, pdf))
        if pp:
            N['report_pp'] = pp

    GR = _opt('genre_removal.json')
    if GR:
        N['score_version'] = str(GR['score_version'])
        N['genre_removed_on'] = GR['removed_on_display']
    TC = _opt('test_counts.json')
    if TC:
        for k in ('backend_tests', 'android_tests', 'ml_guards', 'total_tests'):
            if k in TC:
                N[k] = str(TC[k])

    # ---- hyperparameter studies (ml/hparam_*.py): search on training data only, the
    # test set scored once for the deployed and the search-best config, paired bootstrap.
    # Printed at the JSONs' own 4 decimals, so no value is rounded twice.
    done = 0
    for name, hp in HP_SOURCES.items():
        J = _opt(name)
        if not (J and (J.get('replication') or {}).get('match') and J.get('test')):
            continue
        got = hp['fn'](J)
        if set(got) != set(hp['keys']):
            raise KeyError(f'{name}: hp keys out of sync with HP_SOURCES: '
                           f'{sorted(set(got) ^ set(hp["keys"]))}')
        N.update(got)
        done += 1
    if done == len(HP_SOURCES):
        N['hp_total_configs'] = str(sum(int(N[k]) for k in
                                        ('hp_beh_configs', 'hp_chat_configs', 'hp_voice_configs')))
    return N


def _f4(x):
    return f'{x:.4f}'


def _s4(x):
    return f'{x:+.4f}'


def _hp_common(J, p):
    """Keys every study has: grid size, CV/validation range, deployed CV score and rank,
    test score of the deployed and the search-best config, paired difference and CI."""
    t = J['test']
    return {
        f'{p}_configs': str(J['n_configs']),
        f'{p}_cv_min': _f4(J['cv_spread']['min']),
        f'{p}_cv_max': _f4(J['cv_spread']['max']),
        f'{p}_cv_deployed': _f4(J['cv_deployed']['mean']),
        f'{p}_deployed': _f4(t['deployed']),
        f'{p}_best': _f4(t['best']),
        f'{p}_gain': _s4(t['diff']),
        f'{p}_gain_ci': _ci(t['diff_ci95'], signed=True, nd=4),
    }


def _rf_cfg(p):
    depth = 'unlimited depth' if p['max_depth'] is None else f"depth {p['max_depth']}"
    return f"{p['n_estimators']} trees, {depth}, min leaf {p['min_samples_leaf']}"


def _hp_beh(B):
    t, cost, mr = B['test'], B['cost'], B['marginal_range']
    return {
        **_hp_common(B, 'hp_beh'),
        'hp_beh_rank': str(B['cv_deployed']['rank']),
        'hp_beh_dep_cfg': _rf_cfg(B['cv_deployed']['params']),
        'hp_beh_best_cfg': _rf_cfg(B['best_params']),
        'hp_beh_p_better': _pct(t['p_best_better']),
        'hp_beh_n_test': f"{t['n_test']:,}",
        'hp_beh_depth_effect': _f4(mr['max_depth']),                       # main lever
        'hp_beh_other_effect': _f4(max(v for k, v in mr.items() if k != 'max_depth')),
        'hp_beh_size_deployed': f"{cost['deployed_model_kb'] / 1024:.1f} MB",  # pickled, KiB -> MiB
        'hp_beh_size_best': f"{cost['best_model_kb'] / 1024:.1f} MB",
        'hp_beh_size_x': f"{cost['best_model_kb'] / cost['deployed_model_kb']:.0f}",
        **_hp_beh_survey(B.get('survey_check') or {}),
    }


def _hp_beh_survey(sc):
    """Step 6 of ml/hparam_behaviour.py: the deployed and the CV-best forest scored on the
    IGDS9-SF respondents exactly as ml/eval_behavior_survey.py scores the served model.
    Present only when the survey gate passed (the survey CSV is gitignored)."""
    if not (sc.get('gate', {}).get('match') and 'deployed' in sc and 'best' in sc):
        return {}
    return {
        'hp_beh_survey_n': str(sc['n']),
        'hp_beh_survey_rho_dep': f"{sc['deployed']['rho']:.3f}",
        'hp_beh_survey_rho_best': f"{sc['best']['rho']:.3f}",
        'hp_beh_survey_ci_dep': _ci(sc['deployed']['ci95']),
        'hp_beh_survey_ci_best': _ci(sc['best']['ci95']),
        'hp_beh_survey_diff': f"{sc['diff']:+.3f}",
        'hp_beh_survey_diff_ci': _ci(sc['diff_ci95'], signed=True),
        'hp_beh_survey_p_better': _pct(sc['p_best_better']),
        'hp_beh_survey_boot': f"{sc['bootstrap']['resamples']:,}",
    }


def _hp_chat_in_domain(ids):
    """Step 4 of ml/hparam_chat.py: the same 14-config search selected on a slice of
    CONDA_train only (gaming chat), CONDA_valid untouched."""
    if not ids or 'val_deployed' not in ids:
        return {}
    pp = ids.get('pooled_pick_on_conda_slice') or {}
    out = {
        'hp_chat_id_n': f"{ids['slice']['n_val']:,}",
        'hp_chat_id_prev': f"{ids['slice']['val_prevalence']:.3f}",
        'hp_chat_id_min': _f4(ids['val_spread']['min']),
        'hp_chat_id_max': _f4(ids['val_spread']['max']),
        'hp_chat_id_dep': _f4(ids['val_deployed']['mean']),
        'hp_chat_id_rank': str(ids['val_deployed']['rank']),
        'hp_chat_id_best_c': f"{ids['best_params']['C']:g}",
    }
    if pp:
        out['hp_chat_id_pooled_rank'] = str(pp['rank'])
        out['hp_chat_id_pooled_val'] = _f4(pp['mean'])
    return out


def _hp_chat(C):
    t, rows = C['test'], C['cv_all']
    dep = C['cv_deployed']['mean']
    # the deployed config's own row: its paired difference with itself is exactly zero
    me = [r for r in rows if r['diff_vs_deployed'] == 0 and r['diff_sd'] == 0]
    cm = C['marginal']['C']
    return {
        **_hp_common(C, 'hp_chat'),
        'hp_chat_rank': str(1 + sum(r['mean'] > dep for r in rows)),
        'hp_chat_best_c': f"{C['best_params']['C']:g}",
        'hp_chat_deployed_c': f"{me[0]['params']['C']:g}",
        'hp_chat_c_effect': _f4(max(cm.values()) - min(cm.values())),
        'hp_chat_cw_gap': _f4(C['diagnostics']['class_weight_max_gap']),
        # diagnostic only (never used for selection): best C on the slice's CONDA_train rows
        'hp_chat_conda_part_c': f"{C['diagnostics']['conda_part_argmax_params']['C']:g}",
        # ablation-protocol operating point (compare with chat_p/r_alert_abl, never chat_*_deployed)
        'hp_chat_best_p_alert': f"{t['best_at_alert']['precision']:.3f}",
        'hp_chat_best_r_alert': f"{t['best_at_alert']['recall']:.3f}",
        'hp_chat_n_val': f"{C['cv']['n_val']:,}",
        'hp_chat_n_test': f"{t['n_test']:,}",
        # how much of the pooled validation slice was gaming chat (CONDA_train-origin rows)
        'hp_chat_val_conda_n': f"{C['cv']['n_val_from_conda_train']:,}",
        'hp_chat_val_conda_pct': f"{100 * C['cv']['n_val_from_conda_train'] / C['cv']['n_val']:.0f}%",
        **_hp_chat_in_domain(C.get('in_domain_selection')),
    }


def _hp_voice(V):
    t, d = V['test'], V['test']['discordant']
    return {
        **_hp_common(V, 'hp_voice'),
        'hp_voice_rank': str(V['cv_deployed']['rank']),
        'hp_voice_cv_std': _f4(V['cv_deployed']['std']),
        'hp_voice_lever': _f4(max(V['marginal_range'].values())),
        'hp_voice_p_better': _pct(t['p_best_better']),
        'hp_voice_net_clips': str(d['best_only_correct'] - d['deployed_only_correct']),
        'hp_voice_test_clips': f"{V['data']['test_rows']:,}",
        'hp_voice_test_speakers': str(V['data']['test_speakers']),
        'hp_voice_iters_deployed': str(t['n_iter_used']['deployed']),
        'hp_voice_iter_cap': str(V['deployed_params']['max_iter']),
    }


_HP_COMMON = ('configs', 'cv_min', 'cv_max', 'cv_deployed', 'deployed', 'best', 'gain', 'gain_ci')
HP_SOURCES = {
    'hparam_behaviour.json': {
        'fn': _hp_beh, 'script': 'ml/hparam_behaviour.py',
        'keys': tuple('hp_beh_' + k for k in _HP_COMMON) + (
            'hp_beh_rank', 'hp_beh_dep_cfg', 'hp_beh_best_cfg', 'hp_beh_p_better',
            'hp_beh_n_test', 'hp_beh_depth_effect', 'hp_beh_other_effect',
            'hp_beh_size_deployed', 'hp_beh_size_best', 'hp_beh_size_x',
            'hp_beh_survey_n', 'hp_beh_survey_rho_dep', 'hp_beh_survey_rho_best',
            'hp_beh_survey_ci_dep', 'hp_beh_survey_ci_best', 'hp_beh_survey_diff',
            'hp_beh_survey_diff_ci', 'hp_beh_survey_p_better', 'hp_beh_survey_boot')},
    'hparam_chat.json': {
        'fn': _hp_chat, 'script': 'ml/hparam_chat.py',
        'keys': tuple('hp_chat_' + k for k in _HP_COMMON) + (
            'hp_chat_rank', 'hp_chat_best_c', 'hp_chat_deployed_c', 'hp_chat_c_effect',
            'hp_chat_cw_gap', 'hp_chat_conda_part_c', 'hp_chat_best_p_alert', 'hp_chat_best_r_alert',
            'hp_chat_n_val', 'hp_chat_n_test', 'hp_chat_val_conda_n', 'hp_chat_val_conda_pct',
            'hp_chat_id_n', 'hp_chat_id_prev', 'hp_chat_id_min', 'hp_chat_id_max',
            'hp_chat_id_dep', 'hp_chat_id_rank', 'hp_chat_id_best_c',
            'hp_chat_id_pooled_rank', 'hp_chat_id_pooled_val')},
    'hparam_voice.json': {
        'fn': _hp_voice, 'script': 'ml/hparam_voice.py',
        'keys': tuple('hp_voice_' + k for k in _HP_COMMON) + (
            'hp_voice_rank', 'hp_voice_cv_std', 'hp_voice_lever', 'hp_voice_p_better',
            'hp_voice_net_clips', 'hp_voice_test_clips', 'hp_voice_test_speakers',
            'hp_voice_iters_deployed', 'hp_voice_iter_cap')},
}


NUM = build()

_HINT = {
    'score_version': 'docs/genre_removal.json (written when the genre weight was removed)',
    'genre_removed_on': 'docs/genre_removal.json',
    'backend_tests': 'docs/test_counts.json (run python tools/count_tests.py)',
    'android_tests': 'docs/test_counts.json (run python tools/count_tests.py)',
    'ml_guards': 'docs/test_counts.json (run python tools/count_tests.py)',
    'total_tests': 'docs/test_counts.json (run python tools/count_tests.py)',
    'report_pp': 'docs/CAPSTONE_REPORT.pdf (build the report first)',
    'ieee_pp': 'docs/IEEE_PAPER.log (build the IEEE paper first)',
    'hp_total_configs': 'all three docs/hparam_*.json (run ml/hparam_behaviour.py, '
                        'ml/hparam_chat.py and ml/hparam_voice.py)',
}
for _name, _hp in HP_SOURCES.items():
    for _k in _hp['keys']:
        _HINT[_k] = (f"docs/{_name} (run python {_hp['script']}; its keys appear once the "
                     f"study has passed its replication gate)")


def fill(s, pending=None):
    """Replace {placeholder}s from NUM. Unknown keys and stray braces raise.

    pending: preview mode only. If a string is given, keys from a not-yet-written
    optional source (genre_removal.json, test_counts.json, the report PDF) render as
    that marker instead of raising, so a draft can be rendered and inspected early.
    Final builds must call fill() without it."""
    if not isinstance(s, str):
        return s

    def rep(mm):
        k = mm.group(1)
        if k not in NUM:
            if pending is not None and k in _HINT:
                return pending
            raise KeyError(f'unknown number placeholder {{{k}}}' +
                           (f' - it comes from {_HINT[k]}' if k in _HINT else ''))
        return NUM[k]

    out = re.sub(r'\{(\w+)\}', rep, s)
    if '{' in out or '}' in out:
        raise ValueError(f'unresolved brace in text: {out[:120]!r}')
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for k, v in NUM.items():
        print(f'{k:22s} {v}')
    missing = [k for k in _HINT if k not in NUM]
    if missing:
        print('\nnot yet available:', ', '.join(missing))
