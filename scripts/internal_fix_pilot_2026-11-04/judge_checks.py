"""Reviewer re-checks of the 2026-11-04 pilot.
(1) decomposition of stamped-pair accuracy into error signal e and writer bias d (own-fail vs own-pass subsets);
(2) within-issue pairs among OTHER writers' stamped patches only (symmetric writer confound, more pairs);
(3) does the Lite layer-8 probe read writer identity (SWE-Fixer) rather than outcome;
(4) issue counts behind the core pairs."""
import sys, json, numpy as np, collections
sys.argv = ["x", "none"]
exec(open("pilot_layers.py").read().split('if __name__ == "__main__":')[0])
from sklearn.metrics import roc_auc_score
rng = np.random.default_rng(0)

def other_pairs(s, y, g, st, own):
    """pairs of two other-writer stamped patches on the same issue with opposite outcomes"""
    out = {}
    for k in np.unique(g):
        i = np.where((g == k) & ~own & st)[0]
        P, Fl = i[y[i] == 1], i[y[i] == 0]
        a = [(s[p] > s[f]) + 0.5 * (s[p] == s[f]) for p in P for f in Fl]
        if a: out[k] = a
    return out

def ci(d):
    ks = list(d); pa = np.mean(sum(d.values(), []))
    bs = [np.mean(sum([d[k] for k in rng.choice(ks, len(ks))], [])) for _ in range(2000)]
    return f"{pa:.2f} [{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}] ({sum(len(v) for v in d.values())} pairs, {len(ks)} issues)"

def subset_pairs(s, y, own, g, st, ownfail):
    out = {}
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i] & st[i]]
        if not len(o): continue
        o = o[0]
        if (y[o] == 0) != ownfail: continue
        a = []
        for j in i[~own[i] & st[i]]:
            if y[j] != y[o]:
                p, f = (o, j) if y[o] == 1 else (j, o); a.append((s[p] > s[f]) + 0.5 * (s[p] == s[f]))
        if a: out[k] = a
    return out

for which in ("heldout", "lite"):
    if which == "heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"]); y = y.astype(int); g = np.array(iss); judges, wf, fd = J9, WRITER_FAMILY, "out31b"
        L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/score_hosted/score.jsonl"))}
    else:
        pids, y, wr, g, X = T.lite(); judges, wf, fd = J7, LITE_WRITERS, "lite31b"
        L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/score_lite/score.jsonl"))}
    own = wr == GW; st = X[G] == 100; panel = panel_mean(X, wr, judges, wf)
    lp = np.nan_to_num(np.array([L.get(p, np.nan) for p in pids]), nan=-30)
    F = T.feats(fd, pids)
    print(f"\n==== {which}: patches {len(y)}, other-writer stamped {(~own & st).sum()} (failing {(~own & st & (y==0)).sum()}), own stamped {(own & st).sum()} (failing {(own & st & (y==0)).sum()})")
    rd = {"outside panel": panel, "Gemma log P(100)": lp}
    for li in (1, 8, 14):
        rd[f"probe L{(li+1)*4} all-others"] = oof(F[:, li], y, g, ~own)
        rd[f"probe L{(li+1)*4} demeaned"] = oof(F[:, li], y, g, ~own, demean=True)
    print("-- (1) decomposition: own-fail acc = 0.5+e-d, own-pass acc = 0.5+e+d")
    for k, s in rd.items():
        a = np.mean(sum(subset_pairs(s, y, own, g, st, True).values(), [])); b = np.mean(sum(subset_pairs(s, y, own, g, st, False).values(), []))
        print(f"  {k:26s} own-fail {a:.2f}  own-pass {b:.2f}  -> e={(a+b)/2-0.5:+.2f}  d(pro-Gemma)={(b-a)/2:+.2f}")
    print("-- (2) within-issue pairs among OTHER writers' stamped patches (opposite outcomes)")
    for k, s in rd.items():
        print(f"  {k:26s} {ci(other_pairs(s, y, g, st, own))}")
    print("-- (3) writer-identity readout among stamped patches: AUROC of readout for writer==w vs rest")
    for k in ("probe L8 all-others", "probe L36 all-others", "probe L60 all-others"):
        s = rd[k]; m = st
        for w in np.unique(wr[m]):
            if (wr[m] == w).sum() >= 10:
                print(f"  {k:22s} writer {w:28s} n={int((wr[m]==w).sum()):3d} AUROC(writer) {roc_auc_score(wr[m]==w, s[m]):.2f}  pass rate {y[m][wr[m]==w].mean():.2f}")
