#!/usr/bin/env python3
"""Exploratory, after addendum 2's result: does reading log P(100) remove the own-vs-other gap, and what does it do to
the top quarter and to the rubber-stamp rate? Hosted answers teacher-forced through the local 31B. No model calls."""
import glob, json, os
import numpy as np
import fresh_judging as fj
import judge_probe_analysis as A
from accept_decision import accept
HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(0)
pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
y = y.astype(int); g = np.array(iss); own = wr == A.W
R = {}
for which in ("hosted", "local"):
    rows = {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(HERE, "..", "data", "lab-runs", "probe", f"score_{which}", "score.jsonl"))}
    lp = np.array([rows[p]["logp100"] for p in pids]); rec = np.array([rows[p]["recorded"] for p in pids], float)
    st_o = own & (rec == 100); st_x = ~own & (rec == 100)
    d = dict(verbal_own=A.auc(y[own], rec[own]), verbal_other=A.auc(y[~own], rec[~own]),
             logp_own=A.auc(y[own], lp[own]), logp_other=A.auc(y[~own], lp[~own]),
             logp_stamped_own=A.auc(y[st_o], lp[st_o]), logp_stamped_other=A.auc(y[st_x], lp[st_x]))
    d["gap_verbal"] = d["verbal_other"] - d["verbal_own"]; d["gap_logp"] = d["logp_other"] - d["logp_own"]
    d["gap_logp_ci95"] = A.boot(lambda i: A.auc(y[i][~own[i]], lp[i][~own[i]]) - A.auc(y[i][own[i]], lp[i][own[i]]), g, rng)
    d["gap_verbal_ci95"] = A.boot(lambda i: A.auc(y[i][~own[i]], rec[i][~own[i]]) - A.auc(y[i][own[i]], rec[i][own[i]]), g, rng)
    # top quarter of own patches: score, ties broken by log P(100)
    o = np.where(own)[0]
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    for name, sc in (("score", rec[o]), ("score_tiebreak_logp100", rec[o] + rk(lp[o])), ("logp100_alone", lp[o])):
        p, f = accept(sc, y[o], 0.25); d[f"top_quarter_{name}"] = float(p / (p + f))
    # rubber-stamp rate with a stricter reading of 100: approve only if P(100) >= t
    for t in (0.5, 0.9, 0.99, 0.999):
        a = lp >= np.log(t)
        d[f"approve_p{t}_own_failing"] = float(a[own & (y == 0)].mean()); d[f"approve_p{t}_other_failing"] = float(a[~own & (y == 0)].mean())
        d[f"approve_p{t}_own_passing"] = float(a[own & (y == 1)].mean()); d[f"approve_p{t}_other_passing"] = float(a[~own & (y == 1)].mean())
    R[which] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}
print(json.dumps(R, indent=1))
