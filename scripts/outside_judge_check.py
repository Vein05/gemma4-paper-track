#!/usr/bin/env python3
"""An outside judge as the check of Gemma 4's own patches (spec/outside-judge-check.md; exploratory).

For each patch set (held-out issues, Mini issues with matched-harness patches, Mini issues with patches from four
harnesses): AUROC of each outside judge, of the outside judges' mean score, and of Gemma plus each judge (mean of
percentile ranks), each minus Gemma's AUROC on the same patches; 2,000 issue resamples, seed 0.

Usage: python3 outside_judge_check.py > derived/outside_judge_check_<date>.json
"""
import collections, json, os

import numpy as np
from scipy.stats import rankdata

from fresh_judging import HERE, RUNS, labels
from self_judging_replication import JUDGES, auroc

W, J = "gemma-4-31b", "gemma4-31b"
OUT = [t for t in JUDGES if t != J]
STALE = {"django__django-11848"}  # label predates the graded patch (changelog 2026-10-06 17:20)


def rows(path):
    return [json.loads(l) for l in open(path)]


def fresh_set(runs, drop=()):
    lab = {i: y for i, y in labels(runs).items() if i not in drop}
    S, meta = collections.defaultdict(dict), {}
    for t in JUDGES:
        for r in rows(os.path.join(HERE, "derived", f"fresh_{t}.jsonl")):
            if r["writer"] == W and r.get("err") is None and r.get("parsed") is not None and r["iid"] in lab:
                S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], lab[r["iid"]])
    return S, meta


def original_set():
    S, meta = collections.defaultdict(dict), {}
    for t in JUDGES:
        for r in rows(os.path.join(HERE, "derived", f"selfpref_{t}.jsonl")):
            if r["writer"] == W and r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], int(r["y"]))
    return S, meta


def analyze(S, meta):
    pids = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    X = {t: np.array([S[p][t] for p in pids], float) for t in JUDGES}
    y = np.array([meta[p][1] for p in pids]); iss = np.array([meta[p][0] for p in pids])
    X["outside_mean"] = np.mean([X[t] for t in OUT], axis=0)
    pr = {t: rankdata(X[t]) / len(pids) for t in OUT}
    for t in OUT:
        X[f"gemma_plus_{t}"] = (rankdata(X[J]) / len(pids) + pr[t]) / 2
    checks = OUT + ["outside_mean"] + [f"gemma_plus_{t}" for t in OUT]

    def diffs(idx):
        g = auroc(X[J][idx], y[idx])
        return {c: auroc(X[c][idx], y[idx]) - g for c in checks}

    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        for c, v in diffs(idx).items():
            boot[c].append(v)
    q = lambda v, a: [round(float(np.nanpercentile(v, a)), 3), round(float(np.nanpercentile(v, 100 - a)), 3)]
    allidx = np.arange(len(pids)); point = diffs(allidx)
    out = dict(n=dict(issues=len(issues), patches=len(pids), failing=int((y == 0).sum()), passing=int((y == 1).sum()),
                      left_out=len(S) - len(pids)),
               gemma_auroc=round(float(auroc(X[J], y)), 3))
    for c in checks:
        out[c] = dict(auroc=round(float(auroc(X[c], y)), 3), minus_gemma=round(float(point[c]), 3),
                      ci95=q(boot[c], 2.5), ci_bonferroni8=q(boot[c], 0.3125))
    return out


def costs():
    res = {}
    for t in JUDGES:
        c = [float(r["cost"]) for r in rows(os.path.join(HERE, "derived", f"fresh_{t}.jsonl"))
             if r.get("cost") not in (None, "None")]
        res[t] = round(sum(c) / len(c), 5) if c else None
    return res


def main():
    out = {"held_out_issues": analyze(*fresh_set(["main-a", "main-b"])),
           "mini_issues_matched_harness": analyze(*fresh_set(["mini50"], STALE)),
           "mini_issues_four_harnesses": analyze(*original_set()),
           "cost_per_call_usd": costs()}
    print(json.dumps({"gemma4-31b": out}, indent=1))


if __name__ == "__main__":
    main()
