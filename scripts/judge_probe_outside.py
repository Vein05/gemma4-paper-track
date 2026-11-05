#!/usr/bin/env python3
"""Addendum 4 of spec/judge-probe.md: the same probe on an outside model's hidden state (Qwen3-32B), against Gemma's.
No model calls.

Usage (from scripts/): python judge_probe_outside.py [qwen32b] > derived/judge_probe_outside_2026-11-02.json
"""
import json, os, sys

import numpy as np

import fresh_judging as fj
import judge_probe_analysis as A

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "data", "lab-runs", "probe")


def main():
    other = sys.argv[1] if len(sys.argv) > 1 else "qwen32b"
    rng = np.random.default_rng(0)
    pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
    y = y.astype(int); g = np.array(iss); own = wr == A.W
    stamped = own & (X["gemma4-31b"] == 100)
    sc, folds = {}, {}
    for name in ("out31b", other):
        Z = np.load(os.path.join(PROBE, name, "feats.npz"))
        F = np.stack([Z[p].astype(np.float32) for p in pids])
        sc[name], folds[name] = A.oof(F, y, g, ~own)
    R = {}
    for name, s in sc.items():
        R[name] = dict(own_auroc=A.auc(y[own], s[own]), stamped_auroc=A.auc(y[stamped], s[stamped]),
                       other_auroc=A.auc(y[~own], s[~own]),
                       own_auroc_ci95=A.boot(lambda i: A.auc(y[i][own[i]], s[i][own[i]]), g, rng),
                       stamped_auroc_ci95=A.boot(lambda i: A.auc(y[i][stamped[i]], s[i][stamped[i]]), g, rng),
                       folds=folds[name])
    a, b = sc["out31b"], sc[other]
    R["gemma_minus_outside_stamped"] = A.auc(y[stamped], a[stamped]) - A.auc(y[stamped], b[stamped])
    R["gemma_minus_outside_stamped_ci95"] = A.boot(
        lambda i: A.auc(y[i][stamped[i]], a[i][stamped[i]]) - A.auc(y[i][stamped[i]], b[i][stamped[i]]), g, rng)
    R["gemma_minus_outside_own"] = A.auc(y[own], a[own]) - A.auc(y[own], b[own])
    R["gemma_minus_outside_own_ci95"] = A.boot(
        lambda i: A.auc(y[i][own[i]], a[i][own[i]]) - A.auc(y[i][own[i]], b[i][own[i]]), g, rng)
    R["gemma_minus_outside_other"] = A.auc(y[~own], a[~own]) - A.auc(y[~own], b[~own])
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    R["both_probes_rank_mean_stamped_auroc"] = A.auc(y[stamped], (rk(a) + rk(b))[stamped])  # exploratory
    print(json.dumps(R, indent=1, default=lambda v: round(v, 3) if isinstance(v, float) else v))


if __name__ == "__main__":
    main()
