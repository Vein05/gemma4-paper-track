#!/usr/bin/env python3
"""Pass/fail patches from public SWE-bench-Live submissions (lite split, 300 Python issues, created 2024-10-01 to
2025-03-30), for the before/after training-cutoff test (`spec/post-cutoff-test.md`).

Data in `data/public/swe-bench-live/` (see `data/README.md`): each submission's `<name>__preds.json` (patch per issue)
and `<name>__results.json` (resolved / unresolved issue ids from the SWE-bench-Live evaluation), plus `lite.parquet`
(issue text and creation date). Issues with an evaluation error, an empty patch or no result are skipped. Patches
longer than MAX_CHARS after test hunks are removed are dropped (43 of 2,694 unique patches, both labels; one is 5.7M
characters), so two patches fit in one prompt.

`load_live` returns the same structure as `api_quickcheck.load`: {issue id: (passing patches, failing patches)},
up to `per_label` of each, test-file hunks removed, duplicate patches dropped, shuffled with `seed`.
"""
import collections, glob, json, os, random

import pyarrow.parquet as pq

from api_quickcheck import strip_tests

MAX_CHARS = 30000


def patches_by_issue(data_dir):
    issues = {r["instance_id"]: r for r in pq.read_table(os.path.join(data_dir, "lite.parquet"),
                                                          columns=["instance_id", "created_at", "problem_statement"]).to_pylist()}
    by = collections.defaultdict(dict)
    for f in sorted(glob.glob(os.path.join(data_dir, "*__results.json"))):
        name = os.path.basename(f)[: -len("__results.json")]
        res = json.load(open(f))
        preds = json.load(open(os.path.join(data_dir, name + "__preds.json")))
        if isinstance(preds, list):
            preds = {p["instance_id"]: p for p in preds}
        pos = set(res.get("resolved_ids") or res.get("success_ids") or [])
        neg = set(res.get("unresolved_ids") or res.get("failure_ids") or [])
        for iid, p in sorted(preds.items()):
            y = 1 if iid in pos else 0 if iid in neg else None
            patch = strip_tests(p.get("model_patch") if isinstance(p, dict) else p)
            if y is None or iid not in issues or not patch or len(patch) > MAX_CHARS:
                continue
            by[iid].setdefault((y, patch), dict(iid=iid, model=name, y=y, patch=patch,
                                                issue=issues[iid]["problem_statement"]))
    return by, issues


def load_live(data_dir, per_label, seed, created_from="0000", created_before="9999", max_issues=None):
    by, issues = patches_by_issue(data_dir)
    rng = random.Random(seed)
    sel = {}
    for iid, uniq in sorted(by.items()):
        if not created_from <= str(issues[iid]["created_at"]) < created_before:
            continue
        pos = [x for (y, _), x in uniq.items() if y == 1]
        neg = [x for (y, _), x in uniq.items() if y == 0]
        if pos and neg:
            rng.shuffle(pos); rng.shuffle(neg)
            sel[iid] = (pos[:per_label], neg[:per_label])
    if max_issues and len(sel) > max_issues:
        keep = sorted(random.Random(seed).sample(sorted(sel), max_issues))
        sel = {i: sel[i] for i in keep}
    return sel
