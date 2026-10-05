#!/usr/bin/env python3
"""Why does Gemma 4 rate its own failing patches high? (spec/own-patch-mechanism.md: F1-F4, and P1 via --gemma-tag).

Reads derived/selfpref_<tag>.jsonl (nine judges, reasoning-first 0-100 scores) on the 388 patches of the 50
SWE-bench Verified Mini issues, plus the patch texts. No model calls.

Usage:
  python3 own_patch_mechanism.py > derived/own_patch_mechanism_<date>.json
  python3 own_patch_mechanism.py --gemma-tag gemma4-31b-think > derived/own_patch_mechanism_think_<date>.json
"""
import argparse, collections, json, os, re, sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from self_judging_replication import FAMILY, JUDGES, OWN, WRITER_FAMILY, auroc, pair_measures  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
G, GW = "gemma4-31b", "gemma-4-31b"
B = 2000
STRATA = [(1, 5), (6, 15), (16, 40), (41, 10 ** 9)]


def load(gemma_tag):
    S, meta = collections.defaultdict(dict), {}
    for t in JUDGES:
        f = gemma_tag if t == G else t
        for l in open(os.path.join(HERE, "derived", f"selfpref_{f}.jsonl")):
            r = json.loads(l)
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], r["y"], r["writer"])
    pids = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    return pids, S, meta, len(S) - len(pids)


def changed_lines(patch):
    out = set()
    for l in patch.splitlines():
        if (l.startswith("+") and not l.startswith("+++")) or (l.startswith("-") and not l.startswith("---")):
            s = re.sub(r"\s+", " ", l[1:]).strip()
            if s:
                out.add(l[0] + s)
    return out


def size_of(patch):
    files = len(re.findall(r"^diff --git ", patch, re.M))
    return len(changed_lines(patch)), files


def ci(v):
    v = np.asarray(v, float)
    return [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]


def boot(issues, by_issue, f, seed=0):
    rng = np.random.default_rng(seed)
    return [f(np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])) for _ in range(B)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--gemma-tag", default=G); a = ap.parse_args()
    pids, S, meta, dropped = load(a.gemma_tag)
    import self_preference as SP
    texts = SP.patches()
    X = {t: np.array([S[p][t] for p in pids], float) for t in JUDGES}
    y = np.array([meta[p][1] for p in pids]); wr = np.array([meta[p][2] for p in pids])
    iss = np.array([meta[p][0] for p in pids]); issues = sorted(set(iss))
    by_issue = {i: np.where(iss == i)[0] for i in issues}
    allidx = np.arange(len(pids))
    outside = [k for k in JUDGES if k != G]
    out = dict(gemma_tag=a.gemma_tag, patches_rated_by_all=len(pids), patches_left_out=dropped)

    # ---- F1: same-issue vs different-issue pair accuracy on Gemma's own patches ----
    def pair_acc(idx, t, same):
        own = idx[wr[idx] == GW]
        P, F = own[y[own] == 1], own[y[own] == 0]
        if len(P) == 0 or len(F) == 0:
            return np.nan
        s = (iss[P][:, None] == iss[F][None, :])
        m = s if same else ~s
        if not m.any():
            return np.nan
        d = X[t][P][:, None] - X[t][F][None, :]
        acc = (d > 0) + 0.5 * (d == 0)
        return float(acc[m].mean())

    def f1(idx, same):
        return pair_acc(idx, G, same) - np.nanmean([pair_acc(idx, k, same) for k in outside])

    own = allidx[wr == GW]
    Pn, Fn = own[y[own] == 1], own[y[own] == 0]
    same_pairs = int((iss[Pn][:, None] == iss[Fn][None, :]).sum())
    res = {}
    for name, same in (("same_issue", True), ("different_issue", False)):
        res[name] = dict(gemma=round(pair_acc(allidx, G, same), 3),
                         outside_mean=round(float(np.nanmean([pair_acc(allidx, k, same) for k in outside])), 3),
                         self_minus_outside=round(f1(allidx, same), 3),
                         ci95=ci(boot(issues, by_issue, lambda idx: f1(idx, same))))
    res["pairs"] = dict(same_issue=same_pairs, different_issue=int(len(Pn) * len(Fn) - same_pairs))
    out["F1_same_vs_different_issue"] = res

    # ---- leniency per patch: Gemma minus outside judges not of the writer's family ----
    def len_of(i):
        ks = [k for k in outside if FAMILY[k] != WRITER_FAMILY[wr[i]]]
        return X[G][i] - np.mean([X[k][i] for k in ks])
    L = np.array([len_of(i) for i in allidx])
    sz = np.array([size_of(texts[p]["patch"])[0] for p in pids]); nf = np.array([size_of(texts[p]["patch"])[1] for p in pids])
    stratum = np.array([next(s for s, (lo, hi) in enumerate(STRATA) if lo <= max(v, 1) <= hi) for v in sz])

    # ---- F2: size-matched leniency ----
    def f2(idx):
        fail = idx[(y[idx] == 0) & (nf[idx] == 1)]
        o, c = fail[wr[fail] == GW], fail[wr[fail] != GW]
        diffs, w = [], []
        for s in range(len(STRATA)):
            os_, cs = o[stratum[o] == s], c[stratum[c] == s]
            if len(os_) and len(cs):
                diffs.append(L[os_].mean() - L[cs].mean()); w.append(len(os_))
        return float(np.average(diffs, weights=w)) if w else np.nan

    def unmatched(idx):
        fail = idx[y[idx] == 0]
        return float(L[fail[wr[fail] == GW]].mean() - L[fail[wr[fail] != GW]].mean())
    fail = allidx[y == 0]
    strata_tab = {}
    for s, (lo, hi) in enumerate(STRATA):
        o = fail[(wr[fail] == GW) & (stratum[fail] == s) & (nf[fail] == 1)]
        c = fail[(wr[fail] != GW) & (stratum[fail] == s) & (nf[fail] == 1)]
        strata_tab[f"{lo}-{hi if hi < 10**9 else 'inf'}"] = dict(
            own_failing_n=int(len(o)), control_failing_n=int(len(c)),
            gemma_leniency_own=round(float(L[o].mean()), 1) if len(o) else None,
            gemma_leniency_control=round(float(L[c].mean()), 1) if len(c) else None)
    out["F2_size_matched"] = dict(
        unmatched_difference=round(unmatched(allidx), 1), unmatched_ci95=ci(boot(issues, by_issue, unmatched)),
        matched_difference_single_file=round(f2(allidx), 1), matched_ci95=ci(boot(issues, by_issue, f2)),
        by_stratum_single_file=strata_tab)

    # ---- F3: agreement with Gemma's own failing attempt ----
    gem_fail = {i: [changed_lines(texts[pids[j]]["patch"]) for j in by_issue[i] if wr[j] == GW and y[j] == 0] for i in issues}
    sim = np.full(len(pids), np.nan)
    for j in fail:
        if wr[j] != GW and gem_fail[iss[j]]:
            c = changed_lines(texts[pids[j]]["patch"])
            sim[j] = max((len(c & g) / len(c | g)) if (c | g) else 0 for g in gem_fail[iss[j]])
    elig = allidx[~np.isnan(sim)]
    med = float(np.median(sim[elig]))

    def dev_of(k, i):  # outside judge k minus the other outside judges (not Gemma, not writer family)
        ks = [m for m in outside if m != k and FAMILY[m] != WRITER_FAMILY[wr[i]]]
        return X[k][i] - np.mean([X[m][i] for m in ks])

    def f3(idx, vals):
        e = idx[~np.isnan(sim[idx])]
        hi, lo = e[sim[e] > med], e[sim[e] <= med]
        return float(vals[hi].mean() - vals[lo].mean()) if len(hi) and len(lo) else np.nan
    controls = {}
    for k in outside:
        if FAMILY[k] in ("gemma",):
            continue
        D = np.array([dev_of(k, i) if not np.isnan(sim[i]) and FAMILY[k] != WRITER_FAMILY[wr[i]] else np.nan for i in allidx])
        Dz = np.where(np.isnan(D), 0, D)
        mask_ok = ~np.isnan(D)
        controls[k] = round(f3(allidx[mask_ok], Dz), 1)
    out["F3_agreement"] = dict(
        eligible_control_failing=int(len(elig)), median_similarity=round(med, 3),
        share_similarity_zero=round(float((sim[elig] == 0).mean()), 3),
        gemma_leniency_high_minus_low=round(f3(allidx, L), 1),
        ci95=ci(boot(issues, by_issue, lambda idx: f3(idx, L))),
        outside_judge_controls_high_minus_low=controls)

    # ---- F4: judging others vs judging yourself; checking Gemma's patches ----
    rep = {}
    for j in OWN:
        w = OWN[j]
        others = allidx[np.array([WRITER_FAMILY[v] != FAMILY[j] for v in wr])]
        pm = pair_measures(allidx, X, y, wr, j, w)
        rep[j] = dict(auroc_on_other_families=round(float(auroc(X[j][others], y[others])), 3),
                      auroc_own=round(float(pm["self_auroc_own"]), 3), self_judging_gap=round(float(pm["gap"]), 3))
    on_gemma = {}
    for t in JUDGES:
        a_ = lambda idx, t=t: auroc(X[t][idx[wr[idx] == GW]], y[idx[wr[idx] == GW]])
        acc = (X[t][own] >= 95)
        tp = int((acc & (y[own] == 1)).sum())
        on_gemma[t] = dict(auroc=round(float(a_(allidx)), 3), ci95=ci(boot(issues, by_issue, a_)),
                           accept_ge95_precision=round(tp / max(1, acc.sum()), 3),
                           accept_ge95_recall=round(tp / max(1, int((y[own] == 1).sum())), 3))
        if t != G:
            on_gemma[t]["gemma_minus_this"] = dict(
                est=round(float(auroc(X[G][own], y[own]) - auroc(X[t][own], y[own])), 3),
                ci95=ci(boot(issues, by_issue, lambda idx, t=t: auroc(X[G][idx[wr[idx] == GW]], y[idx[wr[idx] == GW]])
                             - auroc(X[t][idx[wr[idx] == GW]], y[idx[wr[idx] == GW]]))))
    # P1 primary (same measure as the replication): Gemma's self drop minus the outside judges' mean drop
    g = lambda idx: pair_measures(idx, X, y, wr, G, GW)["gap"]
    out["self_judging_gap"] = dict(est=round(float(g(allidx)), 3), ci95=ci(boot(issues, by_issue, g)),
                                   **{k: round(float(v), 3) for k, v in pair_measures(allidx, X, y, wr, G, GW).items()
                                      if k != "gap"})
    out["F4"] = dict(judges_that_wrote_patches=rep, judging_gemma_patches=on_gemma,
                     gemma_patches=dict(passing=int((y[own] == 1).sum()), failing=int((y[own] == 0).sum())))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
