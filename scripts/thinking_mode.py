#!/usr/bin/env python3
"""Gemma 4 31B as judge with thinking off and on, Mini issues, mixed-harness patches (one source for the thinking
numbers in the paper's Section 3.1 and Supplement Table "think"; written 2026-10-22 after the two had drifted apart).
No model calls.

Patches: those scored by all nine judges with Gemma's thinking off (derived/selfpref_<judge>.jsonl) and also scored by
Gemma with thinking on (derived/selfpref_gemma4-31b-think.jsonl), so both columns use the same patches. Leniency
compares Gemma with the outside judges not of the writer's family, as in own_patch_mechanism.py.

The pair measure follows Chen et al. (2025, arXiv 2504.03846, Section 5.1), who count how often a judge prefers its
own wrong answer to another model's correct one: here, the share of same-issue pairs of Gemma's failing patch and
another writer's passing patch in which Gemma scores its own patch higher (ties reported apart). Added after the
thinking scores were seen (exploratory).

Usage: python3 thinking_mode.py > derived/thinking_mode_2026-10-22.json
"""
import collections, json, os

import numpy as np

from self_judging_replication import FAMILY, JUDGES, WRITER_FAMILY, auroc, pair_measures

HERE = os.path.dirname(os.path.abspath(__file__))
G, GW, B = "gemma4-31b", "gemma-4-31b", 2000


def scores(tag):
    S, meta = {}, {}
    for l in open(os.path.join(HERE, "derived", f"selfpref_{tag}.jsonl")):
        r = json.loads(l)
        if r.get("err") is None and r.get("parsed") is not None:
            S[r["pid"]] = r["parsed"]; meta[r["pid"]] = (r["iid"], int(r["y"]), r["writer"])
    return S, meta


def main():
    per = {t: scores(t) for t in JUDGES}
    think, _ = scores("gemma4-31b-think")
    meta = per[G][1]
    pids = sorted(p for p in meta if all(p in per[t][0] for t in JUDGES) and p in think)
    left_out = sum(1 for p in meta if all(p in per[t][0] for t in JUDGES) and p not in think)
    X = {t: np.array([per[t][0][p] for p in pids], float) for t in JUDGES}
    X["think"] = np.array([think[p] for p in pids], float)
    iss = np.array([meta[p][0] for p in pids]); y = np.array([meta[p][1] for p in pids])
    wr = np.array([meta[p][2] for p in pids])
    own = wr == GW
    outside = [t for t in JUDGES if t != G]
    base = np.array([np.mean([X[t][i] for t in outside if FAMILY[t] != WRITER_FAMILY[wr[i]]]) for i in range(len(pids))])
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}

    def m(idx, mode):
        s = X[G if mode == "off" else "think"]
        o, f = idx[own[idx]], idx[y[idx] == 0]
        of, xf = f[own[f]], f[~own[f]]
        L = s - base
        # same-issue pairs: Gemma's failing patch vs another writer's passing patch
        xp = idx[(~own[idx]) & (y[idx] == 1)]
        same = iss[of][:, None] == iss[xp][None, :]
        d = (s[of][:, None] - s[xp][None, :])[same]
        Xm = dict(X, **{G: s})
        return dict(auroc_own=auroc(s[o], y[o]), auroc_others=auroc(s[idx[~own[idx]]], y[idx[~own[idx]]]),
                    self_judging_gap=pair_measures(idx, Xm, y, wr, G, GW)["gap"],
                    own_failing_ge95=float((s[of] >= 95).mean()), own_failing_100=float((s[of] == 100).mean()),
                    own_failing_below_100_mean=float(s[of][s[of] < 100].mean()),
                    others_failing_ge95=float((s[xf] >= 95).mean()), others_failing_100=float((s[xf] == 100).mean()),
                    leniency_own_failing=float(L[of].mean()), leniency_others_failing=float(L[xf].mean()),
                    leniency_own_minus_others_failing=float(L[of].mean() - L[xf].mean()),
                    pairs_own_failing_above_other_passing=float((d > 0).mean()) if d.size else np.nan,
                    pairs_tied=float((d == 0).mean()) if d.size else np.nan, n_pairs=int(d.size))

    allidx = np.arange(len(pids))
    point = {k: m(allidx, k) for k in ("off", "on")}
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(B):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        a, b = m(idx, "off"), m(idx, "on")
        for k in a:
            boot[(k, "off")].append(a[k]); boot[(k, "on")].append(b[k]); boot[(k, "on_minus_off")].append(b[k] - a[k])
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    out = dict(patches=len(pids), left_out_no_thinking_score=left_out, issues=len(issues),
               own=dict(passing=int((own & (y == 1)).sum()), failing=int((own & (y == 0)).sum())),
               others=dict(passing=int((~own & (y == 1)).sum()), failing=int((~own & (y == 0)).sum())))
    for k in point["off"]:
        if k == "n_pairs":
            out[k] = point["off"][k]; continue
        out[k] = dict(off=round(point["off"][k], 3), off_ci95=ci(boot[(k, "off")]),
                      on=round(point["on"][k], 3), on_ci95=ci(boot[(k, "on")]),
                      on_minus_off=round(point["on"][k] - point["off"][k], 3), on_minus_off_ci95=ci(boot[(k, "on_minus_off")]))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
