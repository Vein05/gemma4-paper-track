#!/usr/bin/env python3
"""Reference-free 'which tests should change' judge: issue text + the broken existing tests and their output, no patch.
Asks a model whether each broken test asserts behaviour the issue asks to change (OUTDATED) or behaviour that must stay
(REGRESSION). Scored against the reference-patch witness from the gate runs by outdated_tests.py.
Run 2026-11-07 on the Mac through OpenRouter:
  python3 outdated_test_judge.py ../data/lab-runs/outdated-tests/judge.jsonl google/gemma-4-31b-it,openai/gpt-oss-120b
The Lite jobs file holds the other team's patches and is not released, so the Lite prompts cannot be rebuilt from
the release."""
import json, os, re, sys, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from selfjudge_matrix import call  # OpenRouter helper used by the project

ROOT = os.path.dirname(HERE)
R = f'{ROOT}/data/lab-runs'
OUT = sys.argv[1]
MODELS = sys.argv[2].split(',')
L = lambda p: [json.loads(l) for l in open(p)]

from datasets import load_dataset
issues = {}
for ds in ('princeton-nlp/SWE-bench_Verified', 'princeton-nlp/SWE-bench_Lite'):
    for r in load_dataset(ds, split='test'):
        issues[r['instance_id']] = r['problem_statement']

jobs = []
for name, rep in (('heldout', 'test-repair'), ('lite', 'lite-repair')):
    for j in L(f'{R}/{rep}/jobs.jsonl'):
        jobs.append((name, j))

def clip(s, n):
    return s if len(s) <= n else s[: n // 2] + '\n[...]\n' + s[-n // 2:]

def prompt(iid, note):
    note = note.rsplit('\nFix the patch so these tests pass again', 1)[0]
    note = note.split('A patch for this issue has already been applied to the repository (see `git diff`). ', 1)[-1]
    return f"""You are reviewing a bug-fix task in a Python repository. You see the issue and a report of existing repository tests
that passed before a proposed fix and fail after it. You do NOT see the proposed fix. Do not guess what the fix did.
Decide only from the issue and the tests' assertions.

ISSUE ({iid}):
<issue>
{clip(issues[iid], 7000)}
</issue>

TEST REPORT:
<report>
{clip(note, 9000)}
</report>

For each broken test listed under "Broken tests", classify it:
- OUTDATED: the test asserts the old behaviour that this issue asks to change. Any correct fix for the issue would also
  make this test fail (the test itself must be updated).
- REGRESSION: the test checks behaviour the issue does not ask to change. A correct fix must keep it passing, so this
  failure is a mistake in the proposed fix.

Answer with JSON only, in this form:
{{"tests": {{"<test name as listed>": "OUTDATED" | "REGRESSION", ...}}, "all_outdated": true | false, "reason": "<one sentence>"}}
"""

def one(name, j, model):
    pr = prompt(j['instance_id'], j['notes']['tests'])
    r = call(model, pr, 1200)
    c = r.get('content') or ''
    m = re.search(r'\{.*\}', c, re.S)
    parsed = None
    if m:
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            try:
                parsed = json.loads(re.sub(r'```(json)?', '', m.group(0)))
            except Exception:
                parsed = None
    return dict(set=name, iid=j['instance_id'], pid=j['pid'], model=model, content=c, parsed=parsed, cost=r.get('cost'),
                prompt_tokens=r.get('prompt_tokens'), err=r.get('err'))

done = set()
if os.path.exists(OUT):
    done = {(r['pid'], r['model']) for r in L(OUT) if r.get('parsed') is not None}
todo = [(n, j, m) for m in MODELS for n, j in jobs if (j['pid'], m) not in done]
print('todo', len(todo), file=sys.stderr)
with cf.ThreadPoolExecutor(6) as ex, open(OUT, 'a') as f:
    for res in ex.map(lambda t: one(*t), todo):
        f.write(json.dumps(res) + '\n'); f.flush()
        print(res['iid'], res['model'], res['err'], (res['parsed'] or {}).get('all_outdated'), res['cost'], file=sys.stderr)
