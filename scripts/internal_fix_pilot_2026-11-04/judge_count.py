import sys, json, numpy as np
sys.argv = ["x", "none"]
exec(open("pilot_layers.py").read().split('if __name__ == "__main__":')[0])
rng = np.random.default_rng(0)
def pairs(s, y, own, g, st, other_st_required):
    out = {}
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i] & st[i] & (y[i] == 0)]
        if not len(o): continue
        o = o[0]; a = []
        for j in i[~own[i] & (y[i] == 1)]:
            if other_st_required and not st[j]: continue
            a.append((s[j] > s[o]) + 0.5 * (s[j] == s[o]))
        if a: out[k] = a
    return out
def ci(d):
    ks = list(d); pa = np.mean(sum(d.values(), []))
    bs = [np.mean(sum([d[k] for k in rng.choice(ks, len(ks))], [])) for _ in range(2000)]
    return f"{pa:.2f} [{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}] ({sum(len(v) for v in d.values())} pairs, {len(ks)} issues)"
for which in ("heldout", "lite"):
    if which == "heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"]); y = y.astype(int); g = np.array(iss); judges, wf, fd = J9, WRITER_FAMILY, "out31b"
    else:
        pids, y, wr, g, X = T.lite(); judges, wf, fd = J7, LITE_WRITERS, "lite31b"
    own = wr == GW; st = X[G] == 100; panel = panel_mean(X, wr, judges, wf)
    F = T.feats(fd, pids)
    rd = {"outside panel": panel, "Gemma written score": X[G]}
    for li in (8, 14): rd[f"probe L{(li+1)*4}"] = oof(F[:, li], y, g, ~own)
    print(f"== {which}: Gemma stamped FAILING vs other writer's PASSING on same issue; other patch any Gemma score")
    for k, s in rd.items(): print(f"  {k:22s} {ci(pairs(s, y, own, g, st, False))}")
