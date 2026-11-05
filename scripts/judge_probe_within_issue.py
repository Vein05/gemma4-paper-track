import sys, os, json, numpy as np
sys.path.insert(0, os.getcwd())
import judge_probe_analysis as A, fresh_judging as fj
pids, X, y, wr, iss, S = fj.load(A.NINE, ["main-a", "main-b"])
Z = np.load("../data/lab-runs/probe/out31b/feats.npz")
F = np.stack([Z[p].astype(np.float32) for p in pids]); y = y.astype(int); g = np.array(iss); own = wr == A.W
rng = np.random.default_rng(0)
s, _ = A.oof(F, y, g, ~own)
sh = y.copy()
for k in np.unique(g):
    i = np.where((g == k) & ~own)[0]; sh[i] = rng.permutation(y[i])
s_sh, _ = A.oof(F, y, g, ~own, label_y=sh)
np.savez("../data/lab-runs/probe/oof_scores.npz", s=s, s_sh=s_sh)
def within(sc, mask):
    acc, n = [], 0
    for k in np.unique(g):
        i = np.where((g == k) & mask)[0]; P = i[y[i] == 1]; Fl = i[y[i] == 0]
        if len(P) and len(Fl):
            acc.append(np.mean([(sc[p] > sc[f]) + 0.5 * (sc[p] == sc[f]) for p in P for f in Fl])); n += 1
    return round(float(np.mean(acc)), 3), n
for name, sc in [("probe", s), ("probe, labels shuffled within issue", s_sh), ("31B verbal (hosted)", X["gemma4-31b"]),
                 ("GLM-4.5 verbal", X["glm-4.5"]), ("Kimi-K2 verbal", X["kimi-k2"])]:
    print(f"{name:38s} same-issue pass>fail, all patches {within(sc, np.ones(len(y), bool))}  other writers only {within(sc, ~own)}")
# own patch vs other writers' patches of the same issue: pairs with own failing & other passing, or own passing & other failing
for name, sc in [("probe", s), ("31B verbal (hosted)", X["gemma4-31b"]), ("GLM-4.5 verbal", X["glm-4.5"])]:
    acc = []
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i]]
        if not len(o): continue
        o = o[0]
        for j in i[~own[i]]:
            if y[j] != y[o]:
                p, f = (o, j) if y[o] == 1 else (j, o); acc.append((sc[p] > sc[f]) + 0.5 * (sc[p] == sc[f]))
    print(f"{name:38s} own vs other, same issue, opposite outcome: {np.mean(acc):.3f} (pairs {len(acc)})")
