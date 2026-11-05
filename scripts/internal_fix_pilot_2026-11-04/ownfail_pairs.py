import sys, json, numpy as np
sys.argv = ["x", "none"]
exec(open("pilot_layers.py").read().split('if __name__ == "__main__":')[0])
rng = np.random.default_rng(0)
def pairs(s, y, own, g, st, ownfail):
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
def ci(d):
    ks = list(d); pa = np.mean(sum(d.values(), []))
    bs = [np.mean(sum([d[k] for k in rng.choice(ks, len(ks))], [])) for _ in range(2000)]
    return f"{pa:.2f} [{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}] ({sum(len(v) for v in d.values())} pairs, {len(ks)} issues)"
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
    rd = {"outside panel": panel, "Gemma log P(100)": lp}
    for li in (8, 14):
        rd[f"probe layer {(li+1)*4} (all others)"] = oof(F[:, li], y, g, ~own)
        rd[f"probe layer {(li+1)*4} (others' 100s)"] = oof(F[:, li], y, g, ~own & st)
    print(f"== {which}: Gemma's stamped FAILING patch vs another writer's stamped PASSING patch, same issue")
    for k, s in rd.items(): print(f"  {k:32s} {ci(pairs(s, y, own, g, st, True))}")
    print(f"   (reverse: Gemma's stamped passing vs other's stamped failing)")
    for k, s in rd.items(): print(f"  {k:32s} {ci(pairs(s, y, own, g, st, False))}")
