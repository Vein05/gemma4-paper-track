#!/usr/bin/env python3
"""Addendum of spec/judge-probe.md: (1) the probe trained once on the held-out issues (other writers' patches only)
and applied unchanged to SWE-bench Lite; (2) the held-out probe on the 12B's hidden states. No model calls.

Inputs: ../data/lab-runs/probe/{out31b,lite31b,out12b}/feats.npz.
Usage (from scripts/): python judge_probe_transfer.py > derived/judge_probe_transfer_2026-11-02.json
"""
import collections, json, os

import numpy as np

import fresh_judging as fj
import judge_probe_analysis as A
from accept_decision import accept

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "data", "lab-runs", "probe")
LITE_JUDGES = ["gemma4-31b", "gpt-oss-20b", "gpt-oss-120b", "qwen35-9b", "glm47-flash", "qwen3-coder", "llama-4-maverick"]
G = "gemma-4-31b"


def feats(d, pids):
    Z = np.load(os.path.join(PROBE, d, "feats.npz"))
    miss = [p for p in pids if p not in Z.files]
    assert not miss, f"{d}: {len(miss)} missing"
    return np.stack([Z[p].astype(np.float32) for p in pids])


def lite():
    P = {r["pid"]: r for r in map(json.loads, open(os.path.join(HERE, "..", "data", "public", "third-party-lite",
                                                                 "patches.jsonl")))}
    S = collections.defaultdict(dict)
    for t in LITE_JUDGES:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"lite_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in S.items() if len(s) == len(LITE_JUDGES))
    return (pids, np.array([P[p]["y"] for p in pids], int), np.array([P[p]["writer"] for p in pids]),
            np.array([P[p]["iid"] for p in pids]), {t: np.array([S[p][t] for p in pids], float) for t in LITE_JUDGES})


def measures(s, y, own, stamped, g, rng, verbal):
    auc = A.auc
    d = dict(n_own=int(own.sum()), n_stamped=int(stamped.sum()), n_stamped_failing=int((stamped & (y == 0)).sum()),
             own_auroc=auc(y[own], s[own]), stamped_auroc=auc(y[stamped], s[stamped]),
             other_auroc=auc(y[~own], s[~own]),
             own_auroc_ci95=A.boot(lambda i: auc(y[i][own[i]], s[i][own[i]]), g, rng),
             stamped_auroc_ci95=A.boot(lambda i: auc(y[i][stamped[i]], s[i][stamped[i]]), g, rng),
             verbal_gemma_own_auroc=auc(y[own], verbal[own]), verbal_gemma_other_auroc=auc(y[~own], verbal[~own]))
    o = np.where(own)[0]
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    for name, sc in (("top_quarter_gemma", verbal[o]), ("top_quarter_gemma_tiebreak_probe", verbal[o] + rk(s[o]))):
        p, f = accept(sc, y[o], 0.25); d[name] = float(p / (p + f))
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}


def main():
    rng = np.random.default_rng(0)
    pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
    y = y.astype(int); g = np.array(iss); own = wr == G
    R = {}
    # 1. train once on held-out other writers, apply to Lite
    F = feats("out31b", pids); idx = np.where(~own)[0]
    v, li, C = A.choose(F, y, g, idx)
    m = A.fit(F[idx, li], y[idx], C)
    R["trained_on"] = dict(n=len(idx), layer_index=int(li), C=C, inner_auroc=round(v, 3))
    lp, ly, lw, lg, LX = lite()
    LF = feats("lite31b", lp)
    s = m.predict_proba(LF[:, li])[:, 1]
    lown = lw == G; lstamp = lown & (LX["gemma4-31b"] == 100)
    seen = np.isin(lg, np.unique(g))
    R["lite_overlap"] = dict(lite_issues=int(len(np.unique(lg))), also_in_heldout=int(len(np.unique(lg[seen]))))
    for name, keep in (("lite_unseen_issues", ~seen), ("lite_all_issues", np.ones(len(lp), bool))):
        k = np.where(keep)[0]
        R[name] = measures(s[k], ly[k], lown[k], lstamp[k], lg[k], rng, LX["gemma4-31b"][k])
        R[name]["n_patches"] = len(k)
    # 2. the 12B: same out-of-fold procedure as the held-out primary
    F12 = feats("out12b", pids)
    s12, picks = A.oof(F12, y, g, ~own)
    hosted = X["gemma4-31b"]; stamped = own & (hosted == 100)
    R["heldout_12b"] = measures(s12, y, own, stamped, g, rng, hosted); R["heldout_12b"]["folds"] = picks
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
