#!/usr/bin/env python3
"""Addendum 3 of spec/judge-probe.md: the probe in-domain on LiveCodeBench (no agent). No model calls.

Usage (from scripts/): python judge_probe_lcb.py > derived/judge_probe_lcb_2026-11-02.json
"""
import collections, json, os

import numpy as np

import judge_probe_analysis as A
from accept_decision import accept

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGES = ["gemma4-31b", "gpt-oss-20b", "gpt-oss-120b", "qwen35-9b", "glm47-flash", "llama-4-maverick"]
G = "gemma-4-31b"


def main():
    rng = np.random.default_rng(0)
    P = {r["pid"]: r for r in map(json.loads, open(os.path.join(HERE, "..", "data", "livecodebench-pilot", "judging",
                                                                 "programs.jsonl")))}
    S = collections.defaultdict(dict)
    for t in JUDGES:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"lcb_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    y = np.array([P[p]["y"] for p in pids], int); wr = np.array([P[p]["writer"] for p in pids])
    g = np.array([P[p]["iid"] for p in pids]); hosted = np.array([S[p]["gemma4-31b"] for p in pids], float)
    Z = np.load(os.path.join(HERE, "..", "data", "lab-runs", "probe", "lcb31b", "feats.npz"))
    F = np.stack([Z[p].astype(np.float32) for p in pids])
    own = wr == G; stamped = own & (hosted == 100)
    s, picks = A.oof(F, y, g, ~own)
    d = dict(n=len(pids), n_own=int(own.sum()), n_train_other=int((~own).sum()), n_other_passing=int(y[~own].sum()),
             n_stamped=int(stamped.sum()), n_stamped_failing=int((stamped & (y == 0)).sum()),
             own_auroc=A.auc(y[own], s[own]), stamped_auroc=A.auc(y[stamped], s[stamped]),
             other_auroc=A.auc(y[~own], s[~own]),
             own_auroc_ci95=A.boot(lambda i: A.auc(y[i][own[i]], s[i][own[i]]), g, rng),
             stamped_auroc_ci95=A.boot(lambda i: A.auc(y[i][stamped[i]], s[i][stamped[i]]), g, rng),
             verbal_gemma_own_auroc=A.auc(y[own], hosted[own]), folds=picks)
    o = np.where(own)[0]
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    for name, sc in (("top_quarter_gemma", hosted[o]), ("top_quarter_gemma_tiebreak_probe", hosted[o] + rk(s[o]))):
        p, f = accept(sc, y[o], 0.25); d[name] = float(p / (p + f))
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}, indent=1))


if __name__ == "__main__":
    main()
