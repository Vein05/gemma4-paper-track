#!/usr/bin/env python3
"""Addendum 8 of spec/judge-probe.md: mean of 8 sampled scores (local 31B, temperature 1.0) against log P(100) among
the stamped own patches (hosted 100s). No model calls.

Usage (from scripts/): python judge_probe_sampling.py > derived/judge_probe_sampling_2026-11-02.json
"""
import json, os

import numpy as np

import fresh_judging as fj
import judge_probe_analysis as A
from accept_decision import accept

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "data", "lab-runs", "probe")


def main():
    rng = np.random.default_rng(0)
    pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
    y = y.astype(int); g = np.array(iss); own = wr == A.W
    smp = {r["pid"]: [s for s in r["scores"] if s is not None] for r in map(json.loads, open(os.path.join(PROBE, "sampling_31b.jsonl")))}
    lp = {r["pid"]: r["logp100"] for r in map(json.loads, open(os.path.join(PROBE, "score_hosted", "score.jsonl")))}
    M = np.array([np.mean(smp[p]) if smp.get(p) else np.nan for p in pids])
    L = np.array([lp.get(p, np.nan) for p in pids])
    W = np.asarray(X["gemma4-31b"], float)
    st = own & (W == 100) & ~np.isnan(M) & ~np.isnan(L)
    auc = A.auc
    R = dict(n_sampled=int((~np.isnan(M)).sum()), n_stamped=int(st.sum()), n_stamped_failing=int((st & (y == 0)).sum()),
             mean_parsed_per_patch=float(np.mean([len(v) for v in smp.values()])),
             stamped_all8_are_100=float(np.mean([all(s == 100 for s in smp[p]) for p in np.array(pids)[st]])),
             mean_sampled=auc(y[st], M[st]), logp100=auc(y[st], L[st]),
             mean_sampled_ci95=A.boot(lambda i: auc(y[i][st[i]], M[i][st[i]]), g, rng),
             logp100_ci95=A.boot(lambda i: auc(y[i][st[i]], L[i][st[i]]), g, rng))
    R["logp100_minus_mean_sampled"] = R["logp100"] - R["mean_sampled"]
    R["logp100_minus_mean_sampled_ci95"] = A.boot(
        lambda i: auc(y[i][st[i]], L[i][st[i]]) - auc(y[i][st[i]], M[i][st[i]]), g, rng)
    # exploratory: whole own set and other writers, written vs mean sampled
    o = own & ~np.isnan(M)
    R["own_written"] = auc(y[o], W[o]); R["own_mean_sampled"] = auc(y[o], M[o])
    x = ~own & ~np.isnan(M)
    R["other_written"] = auc(y[x], W[x]); R["other_mean_sampled"] = auc(y[x], M[x])
    oi = np.where(o)[0]
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    for nm, sc in (("written", W[oi]), ("mean_sampled", M[oi])):
        p, f = accept(sc, y[oi], 0.25); R[f"top_quarter_{nm}"] = float(p / (p + f))
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in R.items()}, indent=1))


if __name__ == "__main__":
    main()
