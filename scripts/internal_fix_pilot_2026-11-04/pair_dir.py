import sys, json, numpy as np, collections
sys.argv = ["x", "none"]
exec(open("pilot_layers.py").read().split('if __name__ == "__main__":')[0])
for which in ("heldout","lite"):
    if which=="heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"]); y=y.astype(int); g=np.array(iss); fd="out31b"
    else:
        pids, y, wr, g, X = T.lite(); fd="lite31b"
    own = wr == GW; st = X[G] == 100
    F = T.feats(fd, pids); s = oof(F[:, 1], y, g, ~own)
    res = collections.defaultdict(list)
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i] & st[i]]
        if not len(o): continue
        o = o[0]
        for j in i[~own[i] & st[i]]:
            if y[j] != y[o]:
                p, f = (o, j) if y[o] == 1 else (j, o)
                res[("own fails" if y[o]==0 else "own passes", wr[j])].append((s[p] > s[f]) + 0.5*(s[p]==s[f]))
    print(which, {f"{a}/{b}": (len(v), round(float(np.mean(v)),2)) for (a,b),v in sorted(res.items())})
