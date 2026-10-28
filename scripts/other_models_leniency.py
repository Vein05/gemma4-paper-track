#!/usr/bin/env python3
"""Other models' leniency on their own failing patches, with intervals (spec/other-models-leniency.md).

Reuses the data and leniency definition of self_judging_replication.py (Mini issues, mixed harness, 333 patches scored
by all nine judges). Bootstrap over issues, the same resamples for every self pair. Output is one JSON object keyed by
self pair, plus "pooled", for log_wandb.py.

Usage: python3 other_models_leniency.py > derived/other_models_leniency_<date>.json
"""
import collections, json

import numpy as np

from self_judging_replication import FAMILY, JUDGES, NEW, OWN, WRITER_FAMILY, load, outside

B = 2000
PAIRS = NEW + ["gemma4-31b"]


def lenient(X, wr, j, w):
    """Per-patch leniency of judge j (that wrote as w): j's score minus the outside judges' mean on that patch."""
    out = np.empty(len(wr))
    for i in range(len(wr)):
        ks = [k for k in outside(j, w) if FAMILY[k] != WRITER_FAMILY[wr[i]]]
        out[i] = X[j][i] - np.mean([X[k][i] for k in ks])
    return out


def measures(idx, L, X, y, wr, j, w):
    res = {}
    for lab, yy in (("failing", 0), ("passing", 1)):
        sel = idx[y[idx] == yy]
        own, rest = sel[wr[sel] == w], sel[wr[sel] != w]
        if len(own) == 0 or len(rest) == 0:
            res[f"lenient_difference_{lab}"] = np.nan
            continue
        res[f"lenient_difference_{lab}"] = L[j][own].mean() - L[j][rest].mean()
        if yy == 0:
            res["stamp100_own_failing"] = (X[j][own] == 100).mean()
            res["stamp100_other_failing"] = (X[j][rest] == 100).mean()
    return res


def main():
    pids, S, meta, dropped = load()
    X = {t: np.array([S[p][t] for p in pids], float) for t in JUDGES}
    y = np.array([meta[p][1] for p in pids]); wr = np.array([meta[p][2] for p in pids])
    iss = np.array([meta[p][0] for p in pids]); issues = sorted(set(iss))
    by_issue = {i: np.where(iss == i)[0] for i in issues}
    L = {j: lenient(X, wr, j, OWN[j]) for j in PAIRS}
    allidx = np.arange(len(pids))
    point = {j: measures(allidx, L, X, y, wr, j, OWN[j]) for j in PAIRS}

    rng = np.random.default_rng(0)
    boot = collections.defaultdict(list)
    for _ in range(B):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        m = {j: measures(idx, L, X, y, wr, j, OWN[j]) for j in PAIRS}
        for j in PAIRS:
            for k in ("lenient_difference_failing", "lenient_difference_passing"):
                boot[(j, k)].append(m[j][k])
        pooled = np.nanmean([m[j]["lenient_difference_failing"] for j in NEW])
        boot[("pooled", "f")].append(pooled)
        boot[("gemma_minus_pooled", "f")].append(m["gemma4-31b"]["lenient_difference_failing"] - pooled)

    def ci(v, a):
        v = np.array(v, float); v = v[~np.isnan(v)]
        return [round(float(np.percentile(v, a / 2)), 1), round(float(np.percentile(v, 100 - a / 2)), 1)]

    def nan_count(v):
        return int(np.isnan(np.array(v, float)).sum())

    out = {}
    for j in PAIRS:
        w = OWN[j]
        r = {k: round(float(v), 3 if k.startswith("stamp") else 1) for k, v in point[j].items()}
        for k in ("lenient_difference_failing", "lenient_difference_passing"):
            r[f"{k}_ci95"] = ci(boot[(j, k)], 5)
            r[f"{k}_ci99_bonferroni"] = ci(boot[(j, k)], 1)
            r[f"{k}_resamples_dropped"] = nan_count(boot[(j, k)])
        r["n"] = dict(own_failing=int(((wr == w) & (y == 0)).sum()), own_passing=int(((wr == w) & (y == 1)).sum()),
                      other_failing=int(((wr != w) & (y == 0)).sum()))
        r["spec_role"] = "tested pair" if j in NEW else "reference (not counted)"
        out[j] = r
    pooled_point = float(np.mean([point[j]["lenient_difference_failing"] for j in NEW]))
    out["pooled"] = dict(lenient_difference_failing=round(pooled_point, 1), lenient_difference_failing_ci95=ci(boot[("pooled", "f")], 5),
                         gemma_minus_pooled=round(point["gemma4-31b"]["lenient_difference_failing"] - pooled_point, 1),
                         gemma_minus_pooled_ci95=ci(boot[("gemma_minus_pooled", "f")], 5),
                         pairs=NEW, patches_rated_by_all=len(pids), patches_left_out=dropped, resamples=B, seed=0)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
