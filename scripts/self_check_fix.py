#!/usr/bin/env python3
"""Fixing Gemma 4's own-patch check without training or a second model (spec/self-check-fix.md). No model calls.

Usage: python3 self_check_fix.py > derived/self_check_fix_<date>.json
"""
import collections, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from own_patch_mechanism import changed_lines  # noqa: E402
from self_judging_replication import JUDGES, auroc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GW = "gemma-4-31b"
B = 2000


def scores(tag):
    S = {}
    for l in open(os.path.join(HERE, "derived", f"selfpref_{tag}.jsonl")):
        r = json.loads(l)
        if r.get("err") is None and r.get("parsed") is not None:
            S[r["pid"]] = r
    return S


def main():
    import self_preference as SP
    texts = SP.patches()
    off, think = scores("gemma4-31b"), scores("gemma4-31b-think")
    pids = sorted(p for p in off if off[p]["writer"] == GW and p in think)
    iss = np.array([off[p]["iid"] for p in pids]); y = np.array([off[p]["y"] for p in pids])
    s0 = np.array([off[p]["parsed"] for p in pids], float); st = np.array([think[p]["parsed"] for p in pids], float)
    lines = [changed_lines(texts[p]["patch"]) for p in pids]
    by_issue = collections.defaultdict(list)
    for k, i in enumerate(iss):
        by_issue[i].append(k)

    # S1 attempt agreement; S3 within-issue relative score
    s1 = np.full(len(pids), np.nan); s3 = np.zeros(len(pids))
    for i, ks in by_issue.items():
        for k in ks:
            others = [m for m in ks if m != k]
            if others:
                s1[k] = np.mean([len(lines[k] & lines[m]) / max(1, len(lines[k] | lines[m])) for m in others])
                s3[k] = s0[k] - s0[others].mean()
    s1 = np.where(np.isnan(s1), np.nanmedian(s1), s1)
    z = lambda v: (v - v.mean()) / (v.std() or 1)
    sig = {"S0_gemma_off": s0, "S2_gemma_think": st, "S2_mean_off_think": (s0 + st) / 2,
           "S2_min_off_think": np.minimum(s0, st), "S1_attempt_agreement": s1, "S3_within_issue_relative": s3,
           "C1_S0_plus_S1": z(s0) + z(s1), "C2_meanS2_plus_S1": z((s0 + st) / 2) + z(s1)}

    # outside reference on the subset rated by all eight outside judges
    outside = [t for t in JUDGES if t != "gemma4-31b"]
    O = {t: scores(t) for t in outside}
    has = np.array([all(p in O[t] for t in outside) for p in pids])
    ref = np.array([np.mean([O[t][p]["parsed"] for t in outside]) if h else np.nan for p, h in zip(pids, has)])

    def a(v, idx):
        return auroc(v[idx], y[idx])

    def pair(v, idx, same):
        P, F = idx[y[idx] == 1], idx[y[idx] == 0]
        s = iss[P][:, None] == iss[F][None, :]
        m = s if same else ~s
        d = v[P][:, None] - v[F][None, :]
        return float(((d > 0) + 0.5 * (d == 0))[m].mean()) if m.any() else np.nan

    issues = sorted(by_issue); rng = np.random.default_rng(0)
    draws = [np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))]) for _ in range(B)]
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    allk = np.arange(len(pids))
    out = dict(own_patches=len(pids), passing=int(y.sum()), failing=int((y == 0).sum()), issues=len(issues),
               issues_with_2plus_patches=sum(len(v) > 1 for v in by_issue.values()), signals={})
    for name, v in sig.items():
        r = dict(auroc=round(float(a(v, allk)), 3), ci95=ci([a(v, d) for d in draws]),
                 same_issue_pair_acc=round(pair(v, allk, True), 3), different_issue_pair_acc=round(pair(v, allk, False), 3))
        if name != "S0_gemma_off":
            r["minus_S0"] = round(float(a(v, allk) - a(s0, allk)), 3)
            r["minus_S0_ci95"] = ci([a(v, d) - a(s0, d) for d in draws])
        out["signals"][name] = r
    hk = allk[has]
    out["reference_outside_judges_mean"] = dict(n=int(has.sum()), auroc=round(float(a(ref, hk)), 3),
                                                S0_on_same_subset=round(float(a(s0, hk)), 3),
                                                C1_on_same_subset=round(float(a(sig["C1_S0_plus_S1"], hk)), 3))
    g = out["reference_outside_judges_mean"]
    gap = g["auroc"] - g["S0_on_same_subset"]
    out["share_of_gap_closed_by_C1"] = round((g["C1_on_same_subset"] - g["S0_on_same_subset"]) / gap, 2) if gap > 0 else None
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
