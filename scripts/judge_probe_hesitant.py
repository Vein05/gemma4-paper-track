#!/usr/bin/env python3
"""Addendum 9 of spec/judge-probe.md: pass rate of the 31B's 100s below vs at or above P(100) = 0.999, on SWE-bench Lite
and LiveCodeBench (the cut was chosen on the held-out issues). No model calls.

Usage (from scripts/): python judge_probe_hesitant.py > derived/judge_probe_hesitant_2026-11-02.json
"""
import json, os

import numpy as np

import fresh_judging as fj
import judge_probe_analysis as A
import judge_probe_transfer as T
from judge_probe_logp_replication import lcb

PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "lab-runs", "probe")
CUT = np.log(0.999)


def part(name, pids, y, wr, g, verbal, rng, extra=None):
    rows = {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(PROBE, name, "score.jsonl"))}
    L = np.array([rows[p]["logp100"] if p in rows else np.nan for p in pids])
    own = wr == T.G; ok = ~np.isnan(L)
    out = {}
    sets = {"own": own, "other": ~own}
    if extra is not None:
        sets["own_unseen"] = own & extra
    for nm, m in sets.items():
        t = m & (verbal == 100) & ok
        lo, hi = t & (L < CUT), t & (L >= CUT)

        def diff(i):
            a, b = hi[i], lo[i]
            return y[i][a].mean() - y[i][b].mean() if a.any() and b.any() else np.nan
        out[nm] = dict(n_100=int(t.sum()), n_below=int(lo.sum()), share_below=round(lo.sum() / t.sum(), 3),
                       pass_below=round(y[lo].mean(), 3), pass_above=round(y[hi].mean(), 3),
                       diff=round(y[hi].mean() - y[lo].mean(), 3), diff_ci95=A.boot(diff, g, rng))
    return out


def main():
    rng = np.random.default_rng(0)
    hp, hX, hy, hwr, hiss, _ = fj.load(A.NINE, ["main-a", "main-b"])
    R = {}
    R["heldout_for_reference"] = part("score_hosted", hp, hy.astype(int), hwr, np.array(hiss),
                                      np.asarray(hX["gemma4-31b"], float), rng)
    lp, ly, lw, lg, LX = T.lite()
    R["lite"] = part("score_lite", lp, ly, lw, lg, np.asarray(LX["gemma4-31b"], float), rng,
                     extra=~np.isin(lg, np.unique(hiss)))
    R["livecodebench"] = part("score_lcb", *lcb(), rng)
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
