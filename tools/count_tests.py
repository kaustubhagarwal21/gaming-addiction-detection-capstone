# -*- coding: utf-8 -*-
"""Count the project's automated tests the way CI runs them -> docs/test_counts.json.

Three suites, each counted the way .github/workflows/ci.yml exercises it:

  backend_tests  `python -m pytest tests/` from backend/ (CI jobs backend-tests and
                 backend-tests-postgres run this one suite on SQLite and on Postgres 16;
                 it is counted once). Counted with --collect-only -q, so every collected
                 item counts once, exactly as pytest reports it: each parametrised case
                 separately, skip-marked tests included.
  ml_guards      `python -m pytest ml/tests` from the repo root (CI job
                 research-integrity-guards), counted the same way.
  android_tests  JVM unit tests run by `./gradlew testDebugUnitTest` in each app (CI job
                 android-checks). Gradle is not run here. The script counts @Test
                 annotations under android/<App>/app/src/test after stripping comments and
                 string literals, checks the sources for anything that would make the
                 executed count differ from the annotation count (custom runners,
                 parameterisation, inherited tests, @Ignore), and cross-checks the result
                 against the figure quoted in TESTING.md / README.md and against the last
                 local Gradle run's JUnit XML when one exists.

total_tests = backend_tests + android_tests. Every document already uses this convention
("291 automated tests + 7 research-integrity guards"), so ml_guards stays separate.

Collection safety: the child pytest runs without DATABASE_URL / REQUIRE_DATABASE_URL (the
SQLite CI leg; a count must never open a real database) and with a PRIVATE temp
directory. backend/tests/conftest.py deletes <tempdir>/capstone_test.db when it is
imported, so with the shared temp directory it could delete the database of a test run
that is going on at the same time on this machine.

The script writes nothing if ci.yml no longer contains the invocations it mirrors, if
collection reports errors, or if the per-item listing disagrees with pytest's own
summary line. A wrong count is worse than no count.

Usage:  python tools/count_tests.py            # count and write docs/test_counts.json
        python tools/count_tests.py --dry-run  # count and print only
"""
import argparse
import collections
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'test_counts.json')
CI_YML = os.path.join(ROOT, '.github', 'workflows', 'ci.yml')
APPS = ('ChildApp', 'ParentApp')

# What ci.yml runs, verbatim. Collection swaps only the reporting flag (-v / -q) for
# `--collect-only -q`; verbosity never changes which tests are collected.
PYTEST_SUITES = {
    'backend_tests': {'ci_job': 'backend-tests + backend-tests-postgres (same suite, '
                                'SQLite and Postgres 16 legs; counted once)',
                      'ci_command': 'python -m pytest tests/ -v', 'cwd': 'backend',
                      'paths': ['tests/']},
    'ml_guards': {'ci_job': 'research-integrity-guards',
                  'ci_command': 'python -m pytest ml/tests -q', 'cwd': '.',
                  'paths': ['ml/tests']},
}
ANDROID_CI_COMMAND = './gradlew lintDebug testDebugUnitTest --no-daemon'


class CountError(RuntimeError):
    pass


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------- CI contract
def check_ci_contract():
    """The counts claim to mirror CI. If CI changed how it runs a suite, stop."""
    ci = _read(os.path.relpath(CI_YML, ROOT))
    required = {
        'backend suite command': PYTEST_SUITES['backend_tests']['ci_command'],
        'backend working directory': 'working-directory: backend',
        'ml guard command': PYTEST_SUITES['ml_guards']['ci_command'],
        'android unit-test command': ANDROID_CI_COMMAND,
        'android app matrix': 'app: [ChildApp, ParentApp]',
    }
    missing = [f'{what}: {text!r}' for what, text in required.items() if text not in ci]
    if missing:
        raise CountError('ci.yml no longer contains what this script mirrors; update '
                         'tools/count_tests.py first:\n  ' + '\n  '.join(missing))


# ---------------------------------------------------------------- pytest suites
def _child_env(private_tmp):
    env = dict(os.environ)
    for var in ('DATABASE_URL', 'REQUIRE_DATABASE_URL'):
        env.pop(var, None)
    for var in ('TMPDIR', 'TEMP', 'TMP'):
        env[var] = private_tmp
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def collect(suite):
    spec = PYTEST_SUITES[suite]
    cmd = [sys.executable, '-m', 'pytest', *spec['paths'], '--collect-only', '-q']
    shown = 'python -m pytest ' + ' '.join(spec['paths']) + ' --collect-only -q'
    private_tmp = tempfile.mkdtemp(prefix='count_tests_')
    try:
        proc = subprocess.run(cmd, cwd=os.path.join(ROOT, spec['cwd']),
                              env=_child_env(private_tmp), capture_output=True,
                              text=True, encoding='utf-8', errors='replace', timeout=900)
    finally:
        shutil.rmtree(private_tmp, ignore_errors=True)
    stdout = proc.stdout or ''
    tail = '\n'.join((stdout + '\n' + (proc.stderr or '')).strip().splitlines()[-25:])
    if proc.returncode != 0:
        raise CountError(f'{shown} (in {spec["cwd"]}/) exited {proc.returncode}; '
                         f'refusing to count:\n{tail}')

    # -q listing: one node id per line, then a blank line, then the summary sections.
    ids = []
    for line in stdout.splitlines():
        s = line.strip()
        if not s or s.startswith('='):
            break
        if '::' in s and s.split('::', 1)[0].endswith('.py'):
            ids.append(s)
    m = re.search(r'^(\d+)(?:/\d+)? tests? collected.*$', stdout, re.M)
    if not m:
        raise CountError(f'no "N tests collected" summary in the output of {shown}:\n{tail}')
    if re.search(r'\b\d+ errors?\b', m.group(0)):
        raise CountError(f'{shown} reported collection errors:\n{tail}')
    summary = int(m.group(1))
    if summary != len(ids) or len(set(ids)) != len(ids):
        raise CountError(f'{shown}: summary says {summary} but {len(ids)} items were listed '
                         f'({len(set(ids))} distinct)')
    by_file = collections.Counter(i.split('::', 1)[0] for i in ids)
    return {
        'count': summary,
        'command': shown,
        'cwd': spec['cwd'],
        'ci_command': spec['ci_command'],
        'ci_job': spec['ci_job'],
        'by_file': dict(sorted(by_file.items())),
    }


# ---------------------------------------------------------------- Android
_CHAR_LITERAL = re.compile(r"'(?:\\u[0-9a-fA-F]{4}|\\.|[^'\\\n])'")
_TEST_ANNOTATION = re.compile(r'@(?:[A-Za-z_][\w.]*\.)?Test\b')
_CAVEATS = {
    '@RunWith (custom runner)': re.compile(r'@RunWith\b'),
    '@Parameterized (one method, many executions)': re.compile(r'@Parameterized\b'),
    '@ParameterizedTest': re.compile(r'@ParameterizedTest\b'),
    '@RepeatedTest': re.compile(r'@RepeatedTest\b'),
    '@TestFactory': re.compile(r'@TestFactory\b'),
    '@Ignore / @Disabled (counted, reported as skipped)': re.compile(r'@(?:Ignore|Disabled)\b'),
    'abstract / open class (inherited tests run once per subclass)':
        re.compile(r'\b(?:abstract|open)\s+class\b'),
}


def strip_comments_and_strings(src, kotlin=True):
    """Blank out comments and string/char literal contents (Kotlin or Java), keeping
    newlines, so annotation-like text inside them is never counted. Handles Kotlin
    nested block comments, raw strings and ${...} templates that hold nested strings."""
    out, i, n = [], 0, len(src)
    stack, braces = ['code'], [0]          # 'code' | 'str' | 'raw'; braces per code frame
    while i < n:
        top = stack[-1]
        if top == 'code':
            if src.startswith('//', i):
                j = src.find('\n', i)
                i = n if j < 0 else j
                continue
            if src.startswith('/*', i):
                depth, i = 1, i + 2
                while i < n and depth:
                    if kotlin and src.startswith('/*', i):
                        depth, i = depth + 1, i + 2
                    elif src.startswith('*/', i):
                        depth, i = depth - 1, i + 2
                    else:
                        if src[i] == '\n':
                            out.append('\n')
                        i += 1
                out.append(' ')
                continue
            if src.startswith('"""', i):
                stack.append('raw')
                out.append('"')
                i += 3
                continue
            c = src[i]
            if c == '"':
                stack.append('str')
                out.append('"')
                i += 1
                continue
            if c == "'":
                m = _CHAR_LITERAL.match(src, i)
                if m:
                    out.append("' '")
                    i = m.end()
                    continue
            if c == '{':
                braces[-1] += 1
            elif c == '}':
                if braces[-1] == 0 and len(stack) > 1:   # closes a ${...} template
                    stack.pop()
                    braces.pop()
                    i += 1
                    continue
                braces[-1] -= 1
            out.append(c)
            i += 1
            continue
        raw = top == 'raw'
        if raw and src.startswith('"""', i):
            i += 3
            while i < n and src[i] == '"':
                i += 1
            stack.pop()
            out.append('"')
            continue
        c = src[i]
        if not raw and c == '\\':
            i += 2
            continue
        if not raw and c == '"':
            stack.pop()
            out.append('"')
            i += 1
            continue
        if kotlin and src.startswith('${', i):
            stack.append('code')
            braces.append(0)
            i += 2
            continue
        if c == '\n':
            out.append('\n')
        i += 1
    return ''.join(out)


def _gradle_results(app, sources):
    """Totals from the last local `testDebugUnitTest` run's JUnit XML, if one exists."""
    d = os.path.join(ROOT, 'android', app, 'app', 'build', 'test-results', 'testDebugUnitTest')
    xmls = sorted(glob.glob(os.path.join(d, 'TEST-*.xml')))
    if not xmls:
        return None
    tot = {'tests': 0, 'skipped': 0, 'failures': 0, 'errors': 0}
    for path in xmls:
        root = ET.parse(path).getroot()
        for suite in ([root] if root.tag == 'testsuite' else root.iter('testsuite')):
            for k in tot:
                tot[k] += int(suite.get(k) or 0)
    run_at = max(os.path.getmtime(p) for p in xmls)
    newest_src = max((os.path.getmtime(p) for p in sources), default=0.0)
    tot['run_at'] = datetime.datetime.fromtimestamp(run_at).isoformat(timespec='seconds')
    tot['sources_modified_since_run'] = newest_src > run_at
    return tot


def _docs_quotes():
    quotes = {}
    try:
        m = re.search(r'(\d+) tests across the two apps \((\d+) Child, (\d+) Parent\)',
                      _read('TESTING.md'))
        if m:
            quotes['TESTING.md'] = {'total': int(m.group(1)), 'ChildApp': int(m.group(2)),
                                    'ParentApp': int(m.group(3))}
    except OSError:
        pass
    try:
        m = re.search(r'(\d+) JVM\s+unit tests', _read('README.md'))
        if m:
            quotes['README.md'] = {'total': int(m.group(1))}
    except OSError:
        pass
    return quotes


def count_android():
    by_app, by_file, caveats, gradle = {}, {}, collections.defaultdict(list), {}
    for app in APPS:
        base = os.path.join(ROOT, 'android', app, 'app', 'src', 'test')
        sources = sorted(glob.glob(os.path.join(base, '**', '*.kt'), recursive=True) +
                         glob.glob(os.path.join(base, '**', '*.java'), recursive=True))
        total = 0
        for path in sources:
            with open(path, encoding='utf-8') as f:
                code = strip_comments_and_strings(f.read(), kotlin=path.endswith('.kt'))
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            k = len(_TEST_ANNOTATION.findall(code))
            total += k
            by_file[rel] = k
            for label, rx in _CAVEATS.items():
                if rx.search(code):
                    caveats[label].append(rel)
        by_app[app] = total
        gradle[app] = _gradle_results(app, sources)
    android_total = sum(by_app.values())

    notes, quotes = [], _docs_quotes()
    for doc, q in quotes.items():
        per_app = [a for a in APPS if a in q]
        if q['total'] == android_total and all(q[a] == by_app[a] for a in per_app):
            split = f' ({", ".join(f"{q[a]} {a}" for a in per_app)})' if per_app else ''
            notes.append(f'{doc} quotes {q["total"]}{split}: matches the static count.')
        else:
            diffs = '; '.join(f'{a} {by_app[a]} vs {q[a]} ({by_app[a] - q[a]:+d})'
                              for a in per_app if by_app[a] != q[a])
            notes.append(f'{doc} quotes {q["total"]}, static count is {android_total} '
                         f'({android_total - q["total"]:+d}{"; " + diffs if diffs else ""}): '
                         'tests were added or removed after that document was last synced.')
    for app in APPS:
        g = gradle[app]
        if g is None:
            notes.append(f'{app}: no local Gradle test results to cross-check against.')
            continue
        stale = ' (test sources modified since that run)' if g['sources_modified_since_run'] else ''
        if g['tests'] == by_app[app]:
            notes.append(f'{app}: last local Gradle run ({g["run_at"]}) executed {g["tests"]} '
                         f'tests, {g["skipped"]} skipped: equals the static count{stale}.')
        else:
            notes.append(f'{app}: last local Gradle run ({g["run_at"]}) executed {g["tests"]}, '
                         f'static count is {by_app[app]}{stale}: that run is stale or tests '
                         'were added/removed since.')
    if caveats:
        notes.append('Executed count may differ from the annotation count: ' +
                     '; '.join(f'{k} in {", ".join(v)}' for k, v in sorted(caveats.items())))
    else:
        notes.append('No custom runner, parameterisation, inherited tests or @Ignore in the '
                     'test sources, so each @Test annotation is exactly one executed JVM test.')
    return android_total, {
        'count': android_total,
        'method': 'static count of @Test / @org.junit.Test annotations under '
                  'android/<App>/app/src/test (comments and string literals stripped); '
                  'Gradle is not run by this script',
        'ci_command': ANDROID_CI_COMMAND + ' (in android/ChildApp and android/ParentApp)',
        'ci_job': 'android-checks',
        'by_app': by_app,
        'by_file': by_file,
        'docs_quoted': quotes,
        'gradle_last_local_run': gradle,
        'cross_check': notes,
    }


# ---------------------------------------------------------------- provenance
def _git(*args):
    try:
        p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=60)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _environment():
    try:
        import pytest
        pytest_version = pytest.__version__
    except ImportError:
        pytest_version = None
    dirty = _git('status', '--porcelain', '--', 'backend', 'ml/tests',
                 'android/ChildApp/app/src/test', 'android/ParentApp/app/src/test')
    return {
        'python': sys.version.split()[0],
        'pytest': pytest_version,
        'git_head': _git('rev-parse', '--short', 'HEAD'),
        # split off the status field: _git() strips the output, which eats the leading
        # space of the first porcelain line, so fixed-width slicing clipped a character
        'uncommitted_in_counted_paths': ([ln.split(None, 1)[1] for ln in dirty.splitlines()
                                          if len(ln.split(None, 1)) == 2] if dirty else []),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true', help='print the counts; write nothing')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    try:
        check_ci_contract()
        backend = collect('backend_tests')
        guards = collect('ml_guards')
        android_total, android = count_android()
    except CountError as e:
        sys.exit(f'count_tests: {e}')

    result = {
        'backend_tests': backend['count'],
        'android_tests': android_total,
        'ml_guards': guards['count'],
        'total_tests': backend['count'] + android_total,
        'method': {
            'total_tests': 'backend_tests + android_tests, the documents\' "N automated '
                           'tests + M research-integrity guards" convention; ml_guards '
                           'are counted separately',
            'all_ci_tests_including_guards': backend['count'] + android_total + guards['count'],
            'backend_tests': backend,
            'ml_guards': guards,
            'android_tests': android,
            'collection_environment': 'DATABASE_URL and REQUIRE_DATABASE_URL removed (the '
                                      'SQLite CI leg); private TMPDIR/TEMP/TMP so conftest\'s '
                                      'throwaway DB cannot collide with a concurrent run',
            'environment': _environment(),
        },
        'counted_on': datetime.date.today().isoformat(),
    }

    print(f"backend_tests  {result['backend_tests']:4d}  ({backend['command']}, in backend/)")
    print(f"ml_guards      {result['ml_guards']:4d}  ({guards['command']})")
    print(f"android_tests  {result['android_tests']:4d}  "
          + ', '.join(f'{a} {n}' for a, n in android['by_app'].items()))
    print(f"total_tests    {result['total_tests']:4d}  (backend + android; "
          f"{result['method']['all_ci_tests_including_guards']} with the guards)")
    for note in android['cross_check']:
        print('  - ' + note)
    if args.dry_run:
        print('\n(dry run: nothing written)')
        return
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(f'\nwrote {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
