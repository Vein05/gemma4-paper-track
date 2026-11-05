#!/usr/bin/env python3
"""Addendum 6 of spec/judge-probe.md: log P(100) on SWE-bench Lite and LiveCodeBench (hosted answers teacher-forced
through the local 31B). No model calls.

Usage (from scripts/): python judge_probe_logp_replication.py > derived/judge_probe_logp_replication_2026-11-02.json
"""
import collections, json, os

import numpy as np

import judge_probe_analysis as A
import judge_probe_transfer as T
from accept_decision import accept

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "data", "lab-runs", "probe")
LCB_JUDGES = ["gemma4-31b", "gpt-oss-20b", "gpt-oss-120b", "qwen35-9b", "glm47-flash", "llama-4-maverick"]


def lcb():
    P = {r["pid"]: r for r in map(json.loads, open(os.path.join(HERE, "..", "data", "livecodebench-pilot", "judging",
                                                                 "programs.jsonl")))}
    S = collections.defaultdict(dict)
    for t in LCB_JUDGES:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"lcb_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in S.items() if len(s) == len(LCB_JUDGES))
    return (pids, np.array([P[p]["y"] for p in pids], int), np.array([P[p]["writer"] for p in pids]),
            np.array([P[p]["iid"] for p in pids]), np.array([S[p]["gemma4-31b"] for p in pids], float))


def measures(name, pids, y, wr, g, verbal, rng):
    rows = {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(PROBE, f"score_{name}", "score.jsonl"))}
    keep = np.array([p in rows for p in pids])
    pids = [p for p, k in zip(pids, keep) if k]; y, wr, g, verbal = y[keep], wr[keep], g[keep], verbal[keep]
    lp = np.array([rows[p]["logp100"] for p in pids]); rec = np.array([rows[p]["recorded"] for p in pids], float)
    own = wr == T.G; st = own & (verbal == 100)
    auc = A.auc
    d = dict(n=len(pids), n_missing=int((~keep).sum()), n_own=int(own.sum()), n_stamped=int(st.sum()),
             n_stamped_failing=int((st & (y == 0)).sum()), recorded_matches_verbal=float(np.mean(rec == verbal)),
             K1=auc(y[st], lp[st]), K1_ci95=A.boot(lambda i: auc(y[i][st[i]], lp[i][st[i]]), g, rng),
             own_logp=auc(y[own], lp[own]), other_logp=auc(y[~own], lp[~own]),
             own_verbal=auc(y[own], verbal[own]), other_verbal=auc(y[~own], verbal[~own]))
    d["K2_gap_logp"] = d["other_logp"] - d["own_logp"]; d["gap_verbal"] = d["other_verbal"] - d["own_verbal"]
    d["K2_gap_logp_ci95"] = A.boot(lambda i: auc(y[i][~own[i]], lp[i][~own[i]]) - auc(y[i][own[i]], lp[i][own[i]]), g, rng)
    d["gap_verbal_ci95"] = A.boot(lambda i: auc(y[i][~own[i]], verbal[i][~own[i]]) - auc(y[i][own[i]], verbal[i][own[i]]), g, rng)
    o = np.where(own)[0]
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    for nm, sc in (("score", verbal[o]), ("score_tiebreak_logp100", verbal[o] + rk(lp[o]))):
        p, f = accept(sc, y[o], 0.25); d[f"top_quarter_{nm}"] = float(p / (p + f))
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}


def main():
    rng = np.random.default_rng(0)
    R = {}
    lp, ly, lw, lg, LX = T.lite()
    R["lite"] = measures("lite", lp, ly, lw, lg, LX["gemma4-31b"], rng)
    R["livecodebench"] = measures("lcb", *lcb(), rng)
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
