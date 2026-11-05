"""Pilot (2026-11-04, CPU only, existing activations): where in Gemma 4 31B does the extra trust in its own failing
patches sit, and is there a within-issue, difficulty-free direction that separates stamped failures from stamped passes?

For each readout: (a) excess within-issue leniency in percentile points (Gemma readout's own-failing minus same-issue
other-failing percentile, minus the outside panel's same quantity), (b) same on passing patches, (c) AUROC among
Gemma's stamped own patches, (d) stamped-pair accuracy: on one issue, Gemma's own patch it scored 100 vs another
writer's patch it also scored 100 with the opposite outcome (pass ranked above fail = 1).
Probes: logistic regression C=0.001 on standardized features, trained on other writers' patches only, issue-grouped
5-fold out-of-fold scores. 'demeaned' = trained on features minus the issue mean (label-free), applied to raw features.
"""
import os, sys, json
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

S = "<repo>/scripts"
sys.path.insert(0, S); os.chdir(S)
import fresh_judging as fj
import judge_probe_transfer as T
from per_writer_leniency import J9, J7, LITE_WRITERS
from fresh_judging import FAMILY, WRITER_FAMILY

G, GW = "gemma4-31b", "gemma-4-31b"
PROBE = "<repo>/data/lab-runs/probe"


def panel_mean(X, wr, judges, wfam):
    return np.array([np.mean([X[m][i] for m in judges if m != G and FAMILY[m] != wfam[wr[i]]]) for i in range(len(wr))])


def pct(v):
    v = np.asarray(v, float)
    return 100 * (np.argsort(np.argsort(v + 1e-9 * np.random.default_rng(1).standard_normal(len(v)))) + 0.5) / len(v)


def win_len(p, y, own, g, outcome):
    d = []
    for k in np.unique(g):
        m = g == k
        a, b = p[m & own & (y == outcome)], p[m & ~own & (y == outcome)]
        if len(a) and len(b): d.append(a.mean() - b.mean())
    return np.array(d)


def stamped_pairs(s, y, own, g, stampG):
    acc = []
    for k in np.unique(g):
        i = np.where(g == k)[0]; o = i[own[i] & stampG[i]]
        if not len(o): continue
        o = o[0]
        for j in i[~own[i] & stampG[i]]:
            if y[j] != y[o]:
                p, f = (o, j) if y[o] == 1 else (j, o); acc.append((s[p] > s[f]) + 0.5 * (s[p] == s[f]))
    return np.array(acc, float)


def oof(F, y, g, train, demean=False):
    s = np.full(len(y), np.nan)
    if demean:
        Fd = F.copy()
        for k in np.unique(g):
            m = g == k; Fd[m] -= F[m].mean(0)
    for tr, te in GroupKFold(5).split(np.arange(len(y)), groups=g):
        idx = tr[train[tr]]
        Xtr = Fd[idx] if demean else F[idx]
        m = make_pipeline(StandardScaler(), LogisticRegression(C=0.001, max_iter=3000)).fit(Xtr, y[idx])
        s[te] = m.decision_function(F[te])
    return s


def report(name, s, y, own, g, stampG, panel, rng, B=1000):
    ps, pp = pct(s), pct(panel)
    issues = np.unique(g); pos = {k: np.where(g == k)[0] for k in issues}

    def stat(idx):
        yy, oo, gg, ss, pq, st = y[idx], own[idx], g[idx], ps[idx], pp[idx], stampG[idx]
        # relabel resampled issue copies
        lf = win_len(ss, yy, oo, gg, 0).mean() - win_len(pq, yy, oo, gg, 0).mean()
        lp = win_len(ss, yy, oo, gg, 1).mean() - win_len(pq, yy, oo, gg, 1).mean()
        m = oo & st
        a = roc_auc_score(yy[m], s[idx][m]) if len(set(yy[m])) == 2 else np.nan
        return lf, lp, a
    full = stat(np.arange(len(y)))
    bs = []
    for _ in range(B):
        ks = rng.choice(issues, len(issues))
        idx = np.concatenate([pos[k] for k in ks])
        # make resampled copies distinct issues
        gg_new = np.concatenate([np.full(len(pos[k]), n) for n, k in enumerate(ks)])
        g_save = g
        yy, oo, st = y[idx], own[idx], stampG[idx]
        ss, pq = ps[idx], pp[idx]
        lf = win_len(ss, yy, oo, gg_new, 0).mean() - win_len(pq, yy, oo, gg_new, 0).mean()
        lp = win_len(ss, yy, oo, gg_new, 1).mean() - win_len(pq, yy, oo, gg_new, 1).mean()
        m = oo & st
        a = roc_auc_score(yy[m], s[idx][m]) if len(set(yy[m])) == 2 else np.nan
        bs.append((lf, lp, a))
    bs = np.array(bs)
    ci = lambda c: f"[{np.nanpercentile(bs[:, c], 2.5):+.1f}, {np.nanpercentile(bs[:, c], 97.5):+.1f}]"
    cia = f"[{np.nanpercentile(bs[:, 2], 2.5):.2f}, {np.nanpercentile(bs[:, 2], 97.5):.2f}]"
    sp = stamped_pairs(s, y, own, g, stampG)
    print(f"{name:34s} excess-len fail {full[0]:+5.1f} {ci(0)}  pass {full[1]:+5.1f} {ci(1)}  "
          f"stampedAUROC {full[2]:.3f} {cia}  stampedPairs {sp.mean():.3f} (n={len(sp)})", flush=True)


def run(label, pids, X, y, wr, g, judges, wfam, featdir, extra):
    rng = np.random.default_rng(0)
    own = wr == GW; stampG = X[G] == 100
    panel = panel_mean(X, wr, judges, wfam)
    print(f"\n== {label}: patches {len(y)}, own {own.sum()}, own stamped {(own & stampG).sum()} "
          f"(failing {(own & stampG & (y == 0)).sum()}), stamped pairs {len(stamped_pairs(X[G], y, own, g, stampG))}")
    report("Gemma written score", X[G], y, own, g, stampG, panel, rng)
    for k, v in extra.items():
        report(k, v, y, own, g, stampG, panel, rng)
    if "glm-4.5" in X: report("GLM-4.5 written score", X["glm-4.5"], y, own, g, stampG, panel, rng)
    report("panel mean (reference, =0 by def)", panel, y, own, g, stampG, panel, rng)
    F = T.feats(featdir, pids)
    for li in range(F.shape[1]):
        lay = (li + 1) * 4 if li < 15 else "final"
        s = oof(F[:, li], y, g, ~own)
        report(f"probe layer {lay}", s, y, own, g, stampG, panel, rng, B=300)
        if li in (5, 8, 11, 14):
            s = oof(F[:, li], y, g, ~own, demean=True)
            report(f"  demeaned probe layer {lay}", s, y, own, g, stampG, panel, rng, B=300)


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "heldout":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"])
        y = y.astype(int); g = np.array(iss)
        lp = {}
        for d in ("score_hosted", "score_local"):
            L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/{d}/score.jsonl"))}
            lp[f"log P(100) {d}"] = np.array([L.get(p, np.nan) for p in pids])
        lp = {k: np.nan_to_num(v, nan=np.nanmin(v)) for k, v in lp.items()}
        run("held-out", pids, X, y, wr, g, J9, WRITER_FAMILY, "out31b", lp)
    elif which == "lite":
        pids, y, wr, g, X = T.lite()
        L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/score_lite/score.jsonl"))}
        lp = {"log P(100) hosted answers": np.nan_to_num(np.array([L.get(p, np.nan) for p in pids]), nan=-30)}
        run("lite", pids, X, y, wr, g, J7, LITE_WRITERS, "lite31b", lp)
    elif which == "qwen":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"])
        y = y.astype(int); g = np.array(iss); own = wr == GW; stampG = X[G] == 100
        panel = panel_mean(X, wr, J9, WRITER_FAMILY); rng = np.random.default_rng(0)
        F = T.feats("qwen32b", pids)
        print("== Qwen3-32B activations, held-out (outside-model control)")
        for li in range(F.shape[1]):
            s = oof(F[:, li], y, g, ~own)
            report(f"qwen probe idx {li}", s, y, own, g, stampG, panel, rng, B=300)
    elif which == "scorepos":
        pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"])
        y = y.astype(int); g = np.array(iss); own = wr == GW; stampG = X[G] == 100
        panel = panel_mean(X, wr, J9, WRITER_FAMILY); rng = np.random.default_rng(0)
        Z = np.load(f"{PROBE}/score_hosted/score_feats.npz")
        keep = [i for i, p in enumerate(pids) if p in Z.files]
        print(f"== score-position activations (hosted answers teacher-forced), {len(keep)} of {len(pids)}")
        pids = [pids[i] for i in keep]; y, wr, g, stampG, own, panel = y[keep], wr[keep], g[keep], stampG[keep], own[keep], panel[keep]
        X = {k: v[keep] for k, v in X.items()}
        F = np.stack([Z[p].astype(np.float32) for p in pids])
        report("Gemma written score", X[G], y, own, g, stampG, panel, rng)
        for li in range(F.shape[1]):
            s = oof(F[:, li], y, g, ~own)
            report(f"score-pos probe layer {(li + 1) * 4}", s, y, own, g, stampG, panel, rng, B=300)


def lcb_main():
    import collections
    from per_writer_leniency import LCB_WRITERS, J6
    H = "<repo>"
    P = {r["pid"]: r for r in map(json.loads, open(f"{H}/data/livecodebench-pilot/judging/programs.jsonl"))}
    Sx = collections.defaultdict(dict)
    for t in J6:
        for r in map(json.loads, open(f"{S}/derived/lcb_{t}.jsonl")):
            if r.get("err") is None and r.get("parsed") is not None: Sx[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in Sx.items() if len(s) == len(J6))
    y = np.array([P[p]["y"] for p in pids], int); wr = np.array([P[p]["writer"] for p in pids])
    g = np.array([P[p]["iid"] for p in pids]); X = {t: np.array([Sx[p][t] for p in pids], float) for t in J6}
    L = {r["pid"]: r["logp100"] for r in map(json.loads, open(f"{PROBE}/score_lcb/score.jsonl"))}
    lp = {"log P(100)": np.nan_to_num(np.array([L.get(p, np.nan) for p in pids]), nan=-30)}
    run("livecodebench", pids, X, y, wr, g, J6, LCB_WRITERS, "lcb31b", lp)


if __name__ == "__main__" and sys.argv[1] == "lcb":
    lcb_main()
