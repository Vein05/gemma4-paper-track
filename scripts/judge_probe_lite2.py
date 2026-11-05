#!/usr/bin/env python3
"""Addendum 5 of spec/judge-probe.md: in-domain Lite probe, reverse and pooled transfer, and the label-free verdict
probe. CPU only, saved features. Usage (from scripts/): python judge_probe_lite2.py > derived/judge_probe_lite2_2026-11-02.json
"""
import json, os

import numpy as np
from sklearn.model_selection import GroupKFold

import fresh_judging as fj
import judge_probe_analysis as A
import judge_probe_transfer as T


def oof_masked(F, y, g, train_mask):
    """Out-of-fold scores, issue-grouped folds, training only on train_mask patches of the training issues."""
    s = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(np.arange(len(y)), groups=g):
        idx = tr[train_mask[tr]]
        v, li, C = A.choose(F, y, g, idx)
        s[te] = A.fit(F[idx, li], y[idx], C).predict_proba(F[te, li])[:, 1]
    return s


def train_apply(F, y, g, idx, Ftest):
    v, li, C = A.choose(F, y, g, idx)
    return A.fit(F[idx, li], y[idx], C).predict_proba(Ftest[:, li])[:, 1], dict(layer_index=int(li), C=C, inner=round(v, 3))


def stat(y, s, m, g, rng):
    return dict(auroc=round(A.auc(y[m], s[m]), 3), ci95=A.boot(lambda i: A.auc(y[i][m[i]], s[i][m[i]]), g, rng),
                n=int(m.sum()), n_failing=int((m & (y == 0)).sum()))


def main():
    rng = np.random.default_rng(0)
    hp, hX, hy, hwr, hiss, _ = fj.load(A.NINE, ["main-a", "main-b"])
    hy = hy.astype(int); hg = np.array(hiss); hown = hwr == A.W
    hstamp = hown & (hX["gemma4-31b"] == 100)
    HF = T.feats("out31b", hp)
    lp, ly, lw, lg, LX = T.lite()
    LF = T.feats("lite31b", lp)
    lown = lw == T.G; lstamp = lown & (LX["gemma4-31b"] == 100)
    unseen = ~np.isin(lg, np.unique(hg)); h_notlite = ~np.isin(hg, np.unique(lg))
    R = {}
    # L2 again (probe trained on held-out other writers, applied to Lite), for the paired difference
    sL, info = train_apply(HF, hy, hg, np.where(~hown)[0], LF)
    R["L2"] = stat(ly, sL, lstamp & unseen, lg, rng); R["L2"]["probe"] = info
    # LI2: in-domain Lite
    sLI = oof_masked(LF, ly, lg, ~lown)
    R["LI2"] = stat(ly, sLI, lstamp & unseen, lg, rng)
    m = lstamp & unseen
    R["D2_LI2_minus_L2"] = round(A.auc(ly[m], sLI[m]) - A.auc(ly[m], sL[m]), 3)
    R["D2_ci95"] = A.boot(lambda i: A.auc(ly[i][m[i]], sLI[i][m[i]]) - A.auc(ly[i][m[i]], sL[i][m[i]]), lg, rng)
    R["LI2_own_unseen"] = stat(ly, sLI, lown & unseen, lg, rng)
    # RV2: train on Lite other writers, test on held-out stamped own (issues not in Lite)
    sRV, info = train_apply(LF, ly, lg, np.where(~lown)[0], HF)
    R["RV2"] = stat(hy, sRV, hstamp & h_notlite, hg, rng); R["RV2"]["probe"] = info
    # PO2: pooled other-writer training, issue-grouped folds over the union
    PF = np.concatenate([HF, LF]); py = np.concatenate([hy, ly]); pg = np.concatenate([hg, lg])
    pown = np.concatenate([hown, lown]); src = np.array([0] * len(hy) + [1] * len(ly))
    sPO = oof_masked(PF, py, pg, ~pown)
    mL = np.concatenate([np.zeros(len(hy), bool), lstamp & unseen])
    mH = np.concatenate([hstamp, np.zeros(len(ly), bool)])
    R["PO2_lite"] = stat(py, sPO, mL, pg, rng); R["PO2_heldout"] = stat(py, sPO, mH, pg, rng)
    # VT2: label-free verdict probe (held-out other writers, target hosted score >= 90), applied to Lite
    v = (hX["gemma4-31b"] >= 90).astype(int)
    sVT, info = train_apply(HF, v, hg, np.where(~hown)[0], LF)
    R["VT2"] = stat(ly, sVT, lstamp & unseen, lg, rng); R["VT2"]["probe"] = info
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
