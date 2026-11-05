#!/usr/bin/env python3
"""spec/post-training-familiarity.md: the familiarity test (Gemma pretrained vs instruction-tuned) and the second
model family (OLMo 3 32B pretrained vs instruction-tuned). JSON to stdout.

Usage (from scripts/):
  python post_training_followup.py pilot DIR [DIR ...]
  python post_training_followup.py familiarity --pre-plain D --it-plain D --pre-fam D --it-fam D
  python post_training_followup.py family --g-pre D --g-it D --o-pre D --o-it D
(--g-* read plain.jsonl, --o-* and --*-fam read fam.jsonl)
"""
import argparse, json, os

import numpy as np
from scipy.stats import rankdata

from base_vs_instruct import held, measures, W, B, SEED


def rd(d, name):
    return {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(d, name)) if "skipped" not in l}


def pct(v):
    return 100 * (np.argsort(np.argsort(v)) + 0.5) / len(v)


def ci(v):
    v = np.asarray(v, float)
    return [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]


def centre(x, g):
    out = np.array(x, float)
    for k in np.unique(g):
        m = g == k
        out[m] -= out[m].mean()
    return out


def pilot(a):
    for d in a.dirs:
        R = rd(d, "fam.jsonl")
        pn = [r["p_num"] for r in R.values()]
        print(json.dumps(dict(dir=d, n=len(R), median_p_num=round(float(np.median(pn)), 3),
                              space_moved=sum(r["space_moved"] for r in R.values()), passes=bool(np.median(pn) >= 0.5))))


def boot_issues(iss):
    """Yield (positions, group ids) for B issue resamples; each draw of an issue gets its own group id."""
    ui = np.unique(iss); pos = {k: np.where(iss == k)[0] for k in ui}
    rng = np.random.default_rng(SEED)
    for _ in range(B):
        draw = rng.choice(ui, len(ui))
        yield (np.concatenate([pos[k] for k in draw]),
               np.concatenate([np.full(len(pos[k]), j) for j, k in enumerate(draw)]))


def primary(G, S, g):
    keep = np.isin(g, [k for k in np.unique(g) if (g == k).sum() >= 2])
    G, S, g = G[keep], S[keep], g[keep]
    a, b = centre(rankdata(G), g), centre(rankdata(S), g)
    return float(np.corrcoef(a, b)[0, 1]), int(len(np.unique(g)))


def secondary(G, S, own, g):
    ok = [k for k in np.unique(g) if own[g == k].any() and (~own[g == k]).any()]
    keep = np.isin(g, ok)
    G, S, own, g = G[keep], S[keep], own[keep].astype(float), g[keep]
    s, o, r = centre(S, g), centre(own, g), centre(rankdata(G), g)
    b0 = float(o @ s / (o @ o))
    X = np.stack([o, r], 1)
    b1 = float(np.linalg.lstsq(X, s, rcond=None)[0][0])
    return b0, b1


def familiarity(a):
    pids, y, wr, iss = held()
    pp, pi = rd(a.pre_plain, "plain.jsonl"), rd(a.it_plain, "plain.jsonl")
    fp, fi = rd(a.pre_fam, "fam.jsonl"), rd(a.it_fam, "fam.jsonl")
    keep = [i for i, p in enumerate(pids) if all(p in R for R in (pp, pi, fp, fi))]
    pids = [pids[i] for i in keep]; y, wr, iss = y[keep], wr[keep], iss[keep]
    out = dict(n=len(pids))
    for name, P, Fm in (("pretrained", pp, fp), ("instruct", pi, fi)):
        out[f"check_{name}_logp100_r"] = round(float(np.corrcoef([P[p]["logp100"] for p in pids],
                                                                 [Fm[p]["logp100"] for p in pids])[0, 1]), 5)
    S = pct(np.array([pi[p]["logp100"] for p in pids])) - pct(np.array([pp[p]["logp100"] for p in pids]))
    Fpre = np.array([fp[p]["patch_ll"] / fp[p]["n_patch"] for p in pids])
    Fit = np.array([fi[p]["patch_ll"] / fi[p]["n_patch"] for p in pids])
    G = Fit - Fpre
    own = wr == W
    fail = y == 0
    of, ff = ~own & fail, own & fail
    out["median_F"] = {k: round(float(np.median(v)), 3) for k, v in
                       dict(pre_own_failing=Fpre[ff], pre_other_failing=Fpre[of],
                            it_own_failing=Fit[ff], it_other_failing=Fit[of]).items()}
    out["median_G_own_failing"] = round(float(np.median(G[ff])), 3)
    out["median_G_other_failing"] = round(float(np.median(G[of])), 3)
    lo, hi = np.percentile(G[of], [10, 90])
    out["overlap"] = round(float(((G[ff] >= lo) & (G[ff] <= hi)).mean()), 3)
    # point estimates
    r0, ni = primary(G[of], S[of], iss[of])
    b0, b1 = secondary(G[fail], S[fail], own[fail], iss[fail])
    out.update(primary_r=round(r0, 3), primary_issues=ni, b0=round(b0, 3), b1=round(b1, 3), ratio=round(b1 / b0, 3))
    R, B0, B1, RT = [], [], [], []
    for idx, g in boot_issues(iss):
        m = of[idx]
        R.append(primary(G[idx][m], S[idx][m], g[m])[0])
        m = fail[idx]
        x0, x1 = secondary(G[idx][m], S[idx][m], own[idx][m], g[m])
        B0.append(x0); B1.append(x1); RT.append(x1 / x0 if x0 else np.nan)
    out.update(primary_r_ci=ci(R), b0_ci=ci(B0), b1_ci=ci(B1), ratio_ci=ci(RT))
    pr, rt = out["primary_r_ci"], out["ratio_ci"]
    if pr[0] > 0 and rt[1] < 0.5:
        v = "familiarity explains it"
    elif pr[0] > 0:
        v = "familiarity contributes"
    elif pr[0] <= 0 and rt[0] > 0.5:
        v = "no sign of familiarity"
    else:
        v = "inconclusive"
    out["reading"] = v
    out["secondary_unreliable"] = out["overlap"] < 0.2
    print(json.dumps(out, indent=1))


def family(a):
    pids, y, wr, iss = held()
    R = dict(g_pre=rd(a.g_pre, "plain.jsonl"), g_it=rd(a.g_it, "plain.jsonl"),
             o_pre=rd(a.o_pre, "fam.jsonl"), o_it=rd(a.o_it, "fam.jsonl"))
    keep = [i for i, p in enumerate(pids) if all(p in R[k] for k in R)]
    pids = [pids[i] for i in keep]; y, wr, iss = y[keep], wr[keep], iss[keep]
    pc = {k: pct(np.array([R[k][p]["logp100"] for p in pids])) for k in R}
    full = np.arange(len(pids))
    out = dict(n=len(pids))
    pt = {k: measures(pc[k], y, wr, iss, full) for k in R}
    for k in ("o_pre", "o_it"):
        out[k] = {f: round(v, 3) if isinstance(v, float) else v for f, v in pt[k].items()}
        lp = np.array([R[k][p]["logp100"] for p in pids])
        for nm, m in (("own", (wr == W) & (y == 0)), ("other", (wr != W) & (y == 0))):
            out[k][f"share_p100_above_half_{nm}_failing"] = round(float((np.exp(lp[m]) > 0.5).mean()), 3)
    D = lambda m, p, i: m[i]["leniency"] - m[p]["leniency"]
    out["D_gemma"] = round(D(pt, "g_pre", "g_it"), 3)
    out["D_olmo"] = round(D(pt, "o_pre", "o_it"), 3)
    out["D_gemma_minus_olmo"] = round(out["D_gemma"] - out["D_olmo"], 3)
    ui = np.unique(iss); pos = {k: np.where(iss == k)[0] for k in ui}
    rng = np.random.default_rng(SEED)
    bl = {k: [] for k in R}; bg, bo = [], []
    for _ in range(B):
        idx = np.concatenate([pos[k] for k in rng.choice(ui, len(ui))])
        m = {k: measures(pc[k], y, wr, iss, idx) for k in R}
        for k in R:
            bl[k].append(m[k]["leniency"])
        bg.append(D(m, "g_pre", "g_it")); bo.append(D(m, "o_pre", "o_it"))
    for k in ("o_pre", "o_it"):
        out[k]["leniency_ci"] = ci(bl[k])
    out["D_gemma_ci"], out["D_olmo_ci"] = ci(bg), ci(bo)
    out["D_gemma_minus_olmo_ci"] = ci(np.array(bg) - np.array(bo))
    do, dd = out["D_olmo_ci"], out["D_gemma_minus_olmo_ci"]
    if do[0] > 0 and dd[0] <= 0 <= dd[1]:
        v = "post-training in general"
    elif do[0] > 0 and dd[0] > 0:
        v = "both, Gemma's larger"
    elif do[0] <= 0 and dd[0] > 0:
        v = "specific to Gemma's post-training"
    else:
        v = "inconclusive"
    out["reading"] = v
    # description only: OLMo's familiarity gain on Gemma's failing patches vs other writers' failing patches
    G = np.array([R["o_it"][p]["patch_ll"] / R["o_it"][p]["n_patch"] - R["o_pre"][p]["patch_ll"] / R["o_pre"][p]["n_patch"]
                  for p in pids])
    out["olmo_median_G_own_failing"] = round(float(np.median(G[(wr == W) & (y == 0)])), 3)
    out["olmo_median_G_other_failing"] = round(float(np.median(G[(wr != W) & (y == 0)])), 3)
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("pilot"); p.add_argument("dirs", nargs="+")
    p = sp.add_parser("familiarity")
    for f in ("--pre-plain", "--it-plain", "--pre-fam", "--it-fam"):
        p.add_argument(f, required=True)
    p = sp.add_parser("family")
    for f in ("--g-pre", "--g-it", "--o-pre", "--o-it"):
        p.add_argument(f, required=True)
    a = ap.parse_args()
    {"pilot": pilot, "familiarity": familiarity, "family": family}[a.cmd](a)


if __name__ == "__main__":
    main()
