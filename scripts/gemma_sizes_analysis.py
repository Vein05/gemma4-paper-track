#!/usr/bin/env python3
"""Other Gemma 4 sizes as judges of 31B's held-out patches (spec/gemma-sizes-judges.md, measures fixed before any score).

For each Gemma judge (31B and the given sizes), on the held-out patches scored by the paper's nine judges and every
given size: share of 31B's failing patches and of other writers' failing patches scored 100; leniency (judge minus the
outside judges' mean on the same patch, outside judges as in fresh_judging.analyze) on 31B's failing patches minus on
other writers' failing patches, and the same on passing patches; AUROC on 31B's and on other writers' patches; and, per
size, 31B's leniency difference minus the size's (paired). 95% intervals from 2,000 bootstrap resamples of issues.

Usage: python3 gemma_sizes_analysis.py --sizes gemma4-12b,gemma4-26b-a4b > derived/gemma_sizes_<date>.json
       python3 gemma_sizes_analysis.py --sizes ""   (check: reproduces the paper's 31B numbers)
"""
import argparse, collections, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import fresh_judging as fj  # noqa: E402
from self_judging_replication import auroc  # noqa: E402

NINE = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
        "llama-4-maverick"]
W = "gemma-4-31b"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="gemma4-12b,gemma4-26b-a4b")
    ap.add_argument("--runs", default="main-a,main-b")
    a = ap.parse_args()
    sizes = [s for s in a.sizes.split(",") if s]
    fj.FAMILY.update({s: "gemma" for s in sizes})
    judges = NINE + sizes
    pids, X, y, wr, iss, S = fj.load(judges, a.runs.split(","))
    outside = [k for k in NINE if fj.FAMILY[k] != "gemma"]
    ks_of = [[k for k in outside if fj.FAMILY[k] != fj.WRITER_FAMILY[v]] for v in wr]
    out_mean = np.array([np.mean([X[k][i] for k in ks_of[i]]) for i in range(len(pids))])
    gem = ["gemma4-31b"] + sizes
    D = {j: X[j] - out_mean for j in gem}
    own = wr == W

    def measures(idx):
        m = {}
        for j in gem:
            for lab, yy in (("failing", 0), ("passing", 1)):
                sel = idx[y[idx] == yy]
                o, r = D[j][sel[own[sel]]], D[j][sel[~own[sel]]]
                m[f"{j}_lenient_{lab}_own"] = o.mean()
                m[f"{j}_lenient_{lab}_control"] = r.mean()
                m[f"{j}_lenient_{lab}_difference"] = o.mean() - r.mean()
            m[f"{j}_auroc_own"] = auroc(X[j][idx[own[idx]]], y[idx[own[idx]]])
            m[f"{j}_auroc_control"] = auroc(X[j][idx[~own[idx]]], y[idx[~own[idx]]])
        for s in sizes:
            m[f"31b_minus_{s}_lenient_failing_difference"] = (m["gemma4-31b_lenient_failing_difference"]
                                                               - m[f"{s}_lenient_failing_difference"])
        return m

    allidx = np.arange(len(pids))
    point = measures(allidx)
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(2000):
        m = measures(np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))]))
        for k, v in m.items():
            boot[k].append(v)
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    fail = y == 0
    res = {k: round(float(v), 3) for k, v in point.items()}
    res.update({f"{k}_ci95": ci(boot[k]) for k in point if "difference" in k or "auroc" in k})
    for j in gem:
        res[f"{j}_scored100_own_failing"] = [int((X[j][fail & own] == 100).sum()), int((fail & own).sum())]
        res[f"{j}_scored100_control_failing"] = [int((X[j][fail & ~own] == 100).sum()), int((fail & ~own).sum())]
        res[f"{j}_scored100_own_passing"] = [int((X[j][~fail & own] == 100).sum()), int((~fail & own).sum())]
        res[f"{j}_scored100_control_passing"] = [int((X[j][~fail & ~own] == 100).sum()), int((~fail & ~own).sum())]
    res.update(judges=judges, outside_judges=outside, runs=a.runs.split(","), issues=len(issues),
               patches_rated_by_all=len(pids), patches_left_out=len(S) - len(pids))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
