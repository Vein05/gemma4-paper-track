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
def ci(s, y, own, g, st, rng):
    d = pairs_by_issue(s, y, own, g, st); ks = list(d)
    pt = np.mean(sum(d.values(), []))
    bs = [np.mean(sum([d[k] for k in rng.choice(ks, len(ks))], [])) for _ in range(2000)]
    return f"{pt:.3f} [{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}] issues={len(ks)} pairs={sum(len(v) for v in d.values())}"
rng = np.random.default_rng(0)
for which in ("heldout", "lite"):
    if which == "heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"]); y = y.astype(int); g = np.array(iss)
        L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/score_hosted/score.jsonl"))}
        judges, wf, fd = J9, WRITER_FAMILY, "out31b"
    else:
        pids, y, wr, g, X = T.lite()
        L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/score_lite/score.jsonl"))}
        judges, wf, fd = J7, LITE_WRITERS, "lite31b"
    own = wr == GW; st = X[G] == 100; panel = panel_mean(X, wr, judges, wf)
    lp = np.nan_to_num(np.array([L.get(p, np.nan) for p in pids]), nan=-30)
    F = T.feats(fd, pids)
    print(f"== {which}")
    print("  outside panel mean   ", ci(panel, y, own, g, st, rng))
    if "glm-4.5" in X: print("  GLM-4.5              ", ci(X["glm-4.5"], y, own, g, st, rng))
    print("  Gemma log P(100)     ", ci(lp, y, own, g, st, rng))
    for li in (1, 8, 14):
        s = oof(F[:, li], y, g, ~own); print(f"  probe layer {(li+1)*4:2d}       ", ci(s, y, own, g, st, rng))
