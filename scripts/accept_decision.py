#!/usr/bin/env python3
"""Accepting Gemma 4's own patches without review, by check (spec/accept-decision.md; checks chosen after their AUROCs
were seen, so exploratory in that respect).

For each patch set and check: accept the top share a of Gemma's own patches (a = 25%, 50%, 75%; ties at the cut
accepted at random, in expectation) and report the share of accepted patches that pass and the share of failing
patches accepted; precision minus Gemma's with 95% intervals from 2,000 issue resamples (seed 0); and Gemma's own cut
(every patch it scores 100).

Usage: python3 accept_decision.py > derived/accept_decision_<date>.json
"""
import collections, json

import numpy as np
from scipy.stats import rankdata

from outside_judge_check import STALE, fresh_set, original_set
from self_judging_replication import JUDGES

RATES = (0.25, 0.5, 0.75)
J = "gemma4-31b"


def accept(score, y, a):
    """Expected passes and failures among the top share a of patches by score, ties at the cut broken at random."""
    k = a * len(y)
    v = np.sort(score)[::-1][int(np.ceil(k)) - 1]  # score at the cut
    above, tied = score > v, score == v
    take = (k - above.sum()) / tied.sum()
    passes = y[above].sum() + take * y[tied].sum()
    return passes, k - passes


def table(S, meta):
    pids = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    X = {t: np.array([S[p][t] for p in pids], float) for t in JUDGES}
    y = np.array([meta[p][1] for p in pids]); iss = np.array([meta[p][0] for p in pids])
    pr = lambda t: rankdata(X[t]) / len(pids)
    C = {"gemma": X[J], "gemma_plus_qwen35-9b": (pr(J) + pr("qwen35-9b")) / 2, "glm-4.5": X["glm-4.5"],
         "kimi-k2": X["kimi-k2"]}

    def measures(idx):
        out, nf = {}, (y[idx] == 0).sum()
        for c, sc in C.items():
            for a in RATES:
                p, f = accept(sc[idx], y[idx], a)
                out[(c, a)] = (p / (p + f), f / nf)
        return out

    point = measures(np.arange(len(pids)))
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(2000):
        m = measures(np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))]))
        for c in C:
            for a in RATES:
                boot[(c, a)].append(m[(c, a)][0] - m[("gemma", a)][0])
    ci = lambda v: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]
    top = X[J] == 100
    out = dict(n=dict(patches=len(pids), passing=int(y.sum()), failing=int((y == 0).sum()), issues=len(issues)),
               base_rate=round(float(y.mean()), 3),
               gemma_scores_100=dict(acceptance_rate=round(float(top.mean()), 3),
                                     precision=round(float(y[top].mean()), 3),
                                     failing_accepted=round(float((top & (y == 0)).sum() / (y == 0).sum()), 3)))
    for c in C:
        out[c] = {f"accept_{int(a * 100)}": dict(precision=round(float(point[(c, a)][0]), 3),
                                                 failing_accepted=round(float(point[(c, a)][1]), 3),
                                                 precision_minus_gemma=round(float(point[(c, a)][0] - point[("gemma", a)][0]), 3),
                                                 ci95=ci(boot[(c, a)]))
                  for a in RATES}
    return out


def main():
    out = {"held_out_issues": table(*fresh_set(["main-a", "main-b"])),
           "mini_issues_matched_harness": table(*fresh_set(["mini50"], STALE)),
           "mini_issues_four_harnesses": table(*original_set())}
    print(json.dumps({"gemma4-31b": out}, indent=1))


if __name__ == "__main__":
    main()
