#!/usr/bin/env python3
"""Other models judging their own patches on the held-out issues (spec/other-models-heldout.md).

Loads the held-out patches scored by all nine judges with fresh_judging.load (runs main-a, main-b) and applies the
Mini-issue definitions unchanged: pair_measures of self_judging_replication.py (self-judging gap) and lenient/measures
of other_models_leniency.py (leniency, share scored 100). Gemma's row is the validity check (gap +0.074, leniency
+16.6). Bootstrap over issues, the same resamples for every writer. Output is one JSON object for log_wandb.py.

Usage: python3 other_models_heldout.py > derived/other_models_heldout_<date>.json
"""
import collections, json

import numpy as np

from fresh_judging import load
from other_models_leniency import lenient, measures
from self_judging_replication import JUDGES, NEW, OWN, outside, pair_measures

B = 2000
PAIRS = NEW + ["gemma4-31b"]


def main():
    pids, X, y, wr, iss, S = load(JUDGES, ["main-a", "main-b"])
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    L = {j: lenient(X, wr, j, OWN[j]) for j in PAIRS}
    allidx = np.arange(len(pids))

    def both(idx, j):
        return pair_measures(idx, X, y, wr, j, OWN[j]) | measures(idx, L, X, y, wr, j, OWN[j])

    point = {j: both(allidx, j) for j in PAIRS}
    keys = ["gap", "lenient_difference_failing", "lenient_difference_passing"]
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(B):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        m = {j: both(idx, j) for j in PAIRS}
        for j in PAIRS:
            for k in keys:
                boot[(j, k)].append(m[j][k])
        for k in ("gap", "lenient_difference_failing"):
            pooled = np.nanmean([m[j][k] for j in NEW])
            boot[("pooled", k)].append(pooled)
            boot[("gemma_minus_pooled", k)].append(m["gemma4-31b"][k] - pooled)

    def ci(v, a, nd):
        v = np.array(v, float); v = v[~np.isnan(v)]
        return [round(float(np.percentile(v, a / 2)), nd), round(float(np.percentile(v, 100 - a / 2)), nd)]

    out = {}
    for j in PAIRS:
        w = OWN[j]
        r = {k: round(float(v), 3) for k, v in point[j].items()}
        for k in keys:
            nd = 3 if k == "gap" else 1
            r[f"{k}_ci95"] = ci(boot[(j, k)], 5, nd)
            r[f"{k}_ci99_bonferroni"] = ci(boot[(j, k)], 1, nd)
        r["n"] = dict(own_failing=int(((wr == w) & (y == 0)).sum()), own_passing=int(((wr == w) & (y == 1)).sum()),
                      other_failing=int(((wr != w) & (y == 0)).sum()))
        r["outside_judges"] = outside(j, w)
        r["spec_role"] = "tested writer" if j in NEW else "validity check (published: gap 0.074, leniency 16.6)"
        out[j] = r
    out["pooled"] = dict(
        gap=round(float(np.mean([point[j]["gap"] for j in NEW])), 3), gap_ci95=ci(boot[("pooled", "gap")], 5, 3),
        lenient_difference_failing=round(float(np.mean([point[j]["lenient_difference_failing"] for j in NEW])), 1),
        lenient_difference_failing_ci95=ci(boot[("pooled", "lenient_difference_failing")], 5, 1),
        writers=NEW, issues=len(issues), patches_rated_by_all=len(pids), resamples=B, seed=0)
    for k, nd in (("gap", 3), ("lenient_difference_failing", 1)):  # added after the per-writer results were seen
        out["pooled"][f"gemma_minus_pooled_{k}"] = round(float(point["gemma4-31b"][k] - np.mean([point[j][k] for j in NEW])), nd)
        out["pooled"][f"gemma_minus_pooled_{k}_ci95"] = ci(boot[("gemma_minus_pooled", k)], 5, nd)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
