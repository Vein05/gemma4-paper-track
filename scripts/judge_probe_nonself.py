#!/usr/bin/env python3
"""Addendum 7 of spec/judge-probe.md: gain from reading log P(100) instead of the written score, for the 31B judging
its own patches and for judges that do not judge their own patches here (12B, 26B-A4B, Qwen3-32B). No model calls.

Usage (from scripts/): python judge_probe_nonself.py > derived/judge_probe_nonself_2026-11-02.json
"""
import collections, json, os

import numpy as np

import fresh_judging as fj
import judge_probe_analysis as A

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "data", "lab-runs", "probe")
JUDGES = {"31b-local": "score_local", "31b-hosted": "score_hosted", "12b": "score_12b", "26b-a4b": "score_26b",
          "qwen3-32b": "score_qwen32b", "qwen3-32b-p95": "score_qwen32b_p95"}  # p95: log P("95"), addendum 10


def main():
    rng = np.random.default_rng(0)
    pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
    y = y.astype(int); g = np.array(iss); own = wr == A.W
    L, V = {}, {}
    for j, d in JUDGES.items():
        f = os.path.join(PROBE, d, "score.jsonl")
        if not os.path.exists(f):
            continue
        rows = {json.loads(l)["pid"]: json.loads(l) for l in open(f)}
        L[j] = np.array([rows[p]["logp100"] if p in rows else np.nan for p in pids])
        V[j] = np.array([rows[p]["recorded"] if p in rows else np.nan for p in pids], float)
    ok = np.all([~np.isnan(L[j]) for j in L], axis=0)
    R = {"n_patches_all_judges": int(ok.sum()), "n_own": int((ok & own).sum())}
    auc = A.auc

    def gain(j, m):
        return lambda i: auc(y[i][m[i]], L[j][i][m[i]]) - auc(y[i][m[i]], V[j][i][m[i]])

    mo, mx = ok & own, ok & ~own
    for j in L:
        mode = collections.Counter(V[j][mo]).most_common(1)[0]
        R[j] = dict(own_written=auc(y[mo], V[j][mo]), own_logp=auc(y[mo], L[j][mo]),
                    other_written=auc(y[mx], V[j][mx]), other_logp=auc(y[mx], L[j][mx]),
                    own_tie_share_at_mode=float(mode[1] / mo.sum()), own_mode=float(mode[0]),
                    own_gain_ci95=A.boot(gain(j, mo), g, rng), other_gain_ci95=A.boot(gain(j, mx), g, rng))
        R[j]["own_gain"] = R[j]["own_logp"] - R[j]["own_written"]
        R[j]["other_gain"] = R[j]["other_logp"] - R[j]["other_written"]
        R[j] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in R[j].items()}
    for ref in ("31b-local", "31b-hosted"):
        for j in L:
            if j.startswith("31b"):
                continue
            R[f"{ref}_own_gain_minus_{j}"] = round(R[ref]["own_gain"] - R[j]["own_gain"], 3)
            R[f"{ref}_own_gain_minus_{j}_ci95"] = A.boot(lambda i: gain(ref, mo)(i) - gain(j, mo)(i), g, rng)
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
