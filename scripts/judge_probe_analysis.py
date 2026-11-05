#!/usr/bin/env python3
"""Analysis for spec/judge-probe.md: a linear probe on the local 31B's hidden state at the end of the judging prompt,
trained on other writers' patches only, tested on Gemma's own; plus the issue-likelihood read-out. No model calls.

Inputs: ../data/lab-runs/probe/out31b/feats.npz and issue_ll.jsonl (copied from the lab server).
Usage (from scripts/): python judge_probe_analysis.py [--feats DIR] > derived/judge_probe_2026-11-02.json
"""
import argparse, glob, json, os, sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import fresh_judging as fj
from accept_decision import accept

HERE = os.path.dirname(os.path.abspath(__file__))
NINE = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
        "llama-4-maverick"]
LAYERS = list(range(4, 61, 4))
CS = [0.001, 0.01, 0.1, 1]
W, B = "gemma-4-31b", 2000


def auc(y, s):
    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else float("nan")


def fit(Xtr, ytr, C):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000)).fit(Xtr, ytr)


def choose(F, y, g, idx):
    """Layer and C by inner 5-fold issue-grouped CV on the training patches idx (mean AUROC)."""
    best, inner = None, list(GroupKFold(5).split(idx, groups=g[idx]))
    for li in range(F.shape[1]):
        for C in CS:
            a = []
            for tr, te in inner:
                m = fit(F[idx[tr], li], y[idx[tr]], C)
                a.append(auc(y[idx[te]], m.predict_proba(F[idx[te], li])[:, 1]))
            v = np.nanmean(a)
            if best is None or v > best[0]:
                best = (v, li, C)
    return best


def oof(F, y, g, train_mask, label_y=None):
    """Out-of-fold probe scores for all patches: 5 outer folds grouped by issue; train on train_mask patches of the
    training issues only. label_y replaces the training labels (shuffle control)."""
    ly = y if label_y is None else label_y
    s, picks = np.full(len(y), np.nan), []
    for tr, te in GroupKFold(5).split(np.arange(len(y)), groups=g):
        idx = tr[train_mask[tr]]
        v, li, C = choose(F, ly, g, idx)
        m = fit(F[idx, li], ly[idx], C)
        s[te] = m.predict_proba(F[te, li])[:, 1]
        picks.append(dict(layer=LAYERS[li] if li < len(LAYERS) else "final", C=C, inner_auroc=round(v, 3)))
    return s, picks


def boot(fn, g, rng):
    iss = np.unique(g); pos = {k: np.where(g == k)[0] for k in iss}; out = []
    for _ in range(B):
        idx = np.concatenate([pos[k] for k in rng.choice(iss, len(iss))])
        out.append(fn(idx))
    return [round(float(x), 3) for x in np.nanpercentile(out, [2.5, 97.5])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feats", default=os.path.join(HERE, "..", "data", "lab-runs", "probe", "out31b"))
    a = ap.parse_args()
    pids, X, y, wr, iss, S = fj.load(NINE, ["main-a", "main-b"])
    Z = np.load(os.path.join(a.feats, "feats.npz"))
    keep = [i for i, p in enumerate(pids) if p in Z.files]
    assert len(keep) == len(pids), f"features missing for {len(pids) - len(keep)} patches"
    F = np.stack([Z[p].astype(np.float32) for p in pids])  # (n, layers, d)
    y = y.astype(int); g = np.array(iss); own = wr == W
    local = {}
    for l in open(os.path.join(HERE, "derived", "fresh_gemma4-31b-local.jsonl")):
        r = json.loads(l)
        if r.get("parsed") is not None: local[r["pid"]] = r["parsed"]
    hosted = X["gemma4-31b"]; loc = np.array([local.get(p, np.nan) for p in pids])
    stamped = own & (hosted == 100); stamped_loc = own & (loc == 100)
    rng = np.random.default_rng(0)
    R = dict(n=dict(patches=len(pids), own=int(own.sum()), other=int((~own).sum()), stamped=int(stamped.sum()),
                    stamped_failing=int((stamped & (y == 0)).sum()), stamped_local=int(stamped_loc.sum())))

    def block(s, name):
        d = {"own_auroc": auc(y[own], s[own]), "stamped_auroc": auc(y[stamped], s[stamped]),
             "stamped_local_auroc": auc(y[stamped_loc], s[stamped_loc]), "other_auroc": auc(y[~own], s[~own])}
        d["own_auroc_ci95"] = boot(lambda i: auc(y[i][own[i]], s[i][own[i]]), g, rng)
        d["stamped_auroc_ci95"] = boot(lambda i: auc(y[i][stamped[i]], s[i][stamped[i]]), g, rng)
        d["other_minus_own"] = d["other_auroc"] - d["own_auroc"]
        R[name] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}

    # primary: probe trained on other writers' patches only
    s, picks = oof(F, y, g, ~own); block(s, "probe"); R["probe"]["folds"] = picks
    # verbal judges on the same sets, for reference
    for t in ("gemma4-31b", "glm-4.5", "kimi-k2"):
        block(X[t], f"verbal_{t}")
    block(np.nan_to_num(loc, nan=50), "verbal_gemma4-31b-local")
    # top quarter of Gemma's own patches: Gemma's score, ties broken by the probe (or by fewer model calls)
    calls = {}
    for r in ("main-a", "main-b"):
        for f in glob.glob(os.path.join(fj.RUNS, r, "trajs", "*.json")):
            t = json.load(open(f)); calls[t["instance_id"]] = t["n_calls"]
    nc = np.array([calls.get(i, np.nan) for i in g], float)
    o = np.where(own)[0]
    rk = lambda v: (np.argsort(np.argsort(v)) + 1) / (len(v) + 1)
    tq = {}
    for name, sc in (("gemma", hosted[o]), ("gemma_tiebreak_probe", hosted[o] + rk(s[o])),
                     ("gemma_tiebreak_calls", hosted[o] + rk(-nc[o])), ("probe_alone", s[o])):
        p, f_ = accept(sc, y[o], 0.25); tq[name] = round(float(p / (p + f_)), 3)
    R["top_quarter_own"] = tq
    # controls
    ptxt = {}
    for l in open(os.path.join(HERE, "..", "data", "judge-prompts", "heldout_p1.jsonl")):
        r = json.loads(l); ptxt[r["pid"]] = r["prompt"].split("<patch>\n", 1)[1].rsplit("\n</patch>", 1)[0]
    ln = np.array([np.log1p(sum(len(x) for x in ptxt[p].splitlines() if x[:1] in "+-")) for p in pids])
    s_len, _ = oof(ln[:, None, None], y, g, ~own); block(s_len, "control_patch_length")
    sh = y.copy()
    for k in np.unique(g):  # labels shuffled within issue, training labels only (test labels untouched)
        i = np.where((g == k) & ~own)[0]; sh[i] = rng.permutation(y[i])
    s_sh, _ = oof(F, y, g, ~own, label_y=sh); block(s_sh, "control_shuffled_within_issue")
    s_all, _ = oof(F, y, g, np.ones(len(y), bool)); block(s_all, "control_own_in_training")
    # issue likelihood
    llp = os.path.join(a.feats, "issue_ll.jsonl")
    if os.path.exists(llp):
        L = {json.loads(l)["key"]: json.loads(l)["ll"] for l in open(llp)}
        if all(p in L for p in pids):
            pmi = np.array([L[p] - L["nopatch|" + i] for p, i in zip(pids, g)])
            block(pmi, "issue_likelihood")
    print(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
