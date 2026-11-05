#!/usr/bin/env python3
"""Addendum 2 of spec/judge-probe.md: Gemma's own probability of the score (log P(100), teacher-forced recorded
answers) against the prompt-end probe, and the probe at the score position. No model calls.

Usage (from scripts/): python judge_probe_score.py > derived/judge_probe_score_2026-11-02.json
"""
import json, os

import numpy as np

import fresh_judging as fj
import judge_probe_analysis as A

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "data", "lab-runs", "probe")


def main():
    rng = np.random.default_rng(0)
    pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
    y = y.astype(int); g = np.array(iss); own = wr == A.W
    Z = np.load(os.path.join(PROBE, "out31b", "feats.npz"))
    F = np.stack([Z[p].astype(np.float32) for p in pids])
    s_probe, _ = A.oof(F, y, g, ~own)
    R = {}
    for which, judge_tag in (("hosted", "gemma4-31b"), ("local", "gemma4-31b-local")):
        rows = {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(PROBE, f"score_{which}", "score.jsonl"))}
        assert all(p in rows for p in pids), f"{which}: missing rows"
        lp = np.array([rows[p]["logp100"] for p in pids])
        rec = np.array([rows[p]["recorded"] for p in pids], float)
        stamped = own & (rec == 100)
        d = dict(n_stamped=int(stamped.sum()), n_stamped_failing=int((stamped & (y == 0)).sum()))
        for name, s in (("logp100", lp), ("prompt_end_probe", s_probe)):
            d[f"{name}_own_auroc"] = A.auc(y[own], s[own])
            d[f"{name}_stamped_auroc"] = A.auc(y[stamped], s[stamped])
            d[f"{name}_stamped_auroc_ci95"] = A.boot(lambda i: A.auc(y[i][stamped[i]], s[i][stamped[i]]), g, rng)
        d["probe_minus_logp100_stamped_ci95"] = A.boot(
            lambda i: A.auc(y[i][stamped[i]], s_probe[i][stamped[i]]) - A.auc(y[i][stamped[i]], lp[i][stamped[i]]), g, rng)
        d["probe_minus_logp100_stamped"] = d["prompt_end_probe_stamped_auroc"] - d["logp100_stamped_auroc"]
        # probe at the score position (same out-of-fold procedure)
        Zs = np.load(os.path.join(PROBE, f"score_{which}", "score_feats.npz"))
        Fs = np.stack([Zs[p].astype(np.float32) for p in pids])
        s2, picks = A.oof(Fs, y, g, ~own)
        d["score_position_probe_own_auroc"] = A.auc(y[own], s2[own])
        d["score_position_probe_stamped_auroc"] = A.auc(y[stamped], s2[stamped])
        d["score_position_probe_stamped_auroc_ci95"] = A.boot(lambda i: A.auc(y[i][stamped[i]], s2[i][stamped[i]]), g, rng)
        d["score_position_probe_folds"] = picks
        # does log P(100) add to the probe? simple sum of ranks within stamped (exploratory)
        rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
        d["rank_sum_probe_logp100_stamped_auroc"] = A.auc(y[stamped], (rk(s_probe) + rk(lp))[stamped])
        R[which] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
