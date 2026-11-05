import sys, json, numpy as np
sys.argv = ["x", "none"]
exec(open("pilot_layers.py").read().split('if __name__ == "__main__":')[0])
def pairs_by_issue(s, y, own, g, st):
    out = {}
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i] & st[i]]
        if not len(o): continue
        o = o[0]; a = []
        for j in i[~own[i] & st[i]]:
            if y[j] != y[o]:
                p, f = (o, j) if y[o] == 1 else (j, o); a.append((s[p] > s[f]) + 0.5 * (s[p] == s[f]))
        if a: out[k] = a
    return out
rng = np.random.default_rng(0)
for which in ("heldout", "lite"):
    if which == "heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"]); y = y.astype(int); g = np.array(iss); fd = "out31b"
    else:
        pids, y, wr, g, X = T.lite(); fd = "lite31b"
    own = wr == GW; st = X[G] == 100
    F = T.feats(fd, pids)
    tr = ~own & st
    print(f"== {which}: training on other writers' patches Gemma scored 100: {tr.sum()} ({(tr & (y==0)).sum()} failing)")
    for li in (3, 5, 8, 11, 14):
        for C in (0.001, 0.01):
            s = oof(F[:, li], y, g, tr) if C == 0.001 else None
            if s is None: continue
            m = own & st
            d = pairs_by_issue(s, y, own, g, st); ks = list(d)
            pa = np.mean(sum(d.values(), []))
            bs = [np.mean(sum([d[k] for k in rng.choice(ks, len(ks))], [])) for _ in range(1000)]
            print(f"  layer {(li+1)*4:2d}: own stamped AUROC {roc_auc_score(y[m], s[m]):.3f}  stamped pairs {pa:.3f} [{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}]  other-stamped (in-fold) n/a")
