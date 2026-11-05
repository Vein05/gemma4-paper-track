import sys, json, numpy as np
sys.argv = ["x", "none"]
exec(open("pilot_layers.py").read().split('if __name__ == "__main__":')[0])
R = "<repo>/data/lab-runs"
def pairs_by_issue(s, y, own, g, st):
    out = {}
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i] & st[i]]
        if not len(o): continue
        o = o[0]; a = []
        for j in i[~own[i] & st[i]]:
            if y[j] != y[o] and not np.isnan(s[j]) and not np.isnan(s[o]):
                p, f = (o, j) if y[o] == 1 else (j, o); a.append((s[p] > s[f]) + 0.5 * (s[p] == s[f]))
        if a: out[k] = a
    return out
rng = np.random.default_rng(0)
def ci(s, y, own, g, st):
    d = pairs_by_issue(s, y, own, g, st); ks = list(d)
    pa = np.mean(sum(d.values(), []))
    bs = [np.mean(sum([d[k] for k in rng.choice(ks, len(ks))], [])) for _ in range(2000)]
    return f"{pa:.3f} [{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}] pairs={sum(len(v) for v in d.values())}"
def rd(p): return {r["pid"]: r["logp100"] for r in map(json.loads, open(p))}
for which in ("heldout", "lite"):
    if which == "heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"]); y = y.astype(int); g = np.array(iss)
        files = {"pretrained, plain": f"{R}/base-vs-instruct/bvi_pre/plain.jsonl", "chat bf16, plain": f"{R}/base-vs-instruct/bvi_it/plain.jsonl",
                 "OLMo pretrained": f"{R}/post-training-followup/fam_opre/fam.jsonl", "OLMo instruct": f"{R}/post-training-followup/fam_oit/fam.jsonl"}
    else:
        pids, y, wr, g, X = T.lite()
        files = {"pretrained, plain": f"{R}/pretrained-judge-fix/lite_pre/plain.jsonl", "chat bf16, plain": f"{R}/pretrained-judge-fix/lite_it/plain.jsonl"}
    own = wr == GW; st = X[G] == 100
    print(f"== {which}")
    for k, f in files.items():
        L = rd(f); s = np.array([L.get(p, np.nan) for p in pids], float)
        m = own & st & ~np.isnan(s)
        print(f"  {k:20s} stamped pairs {ci(s, y, own, g, st)}   own stamped AUROC {roc_auc_score(y[m], s[m]):.3f}")
