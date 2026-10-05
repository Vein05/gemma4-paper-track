#!/usr/bin/env python3
"""Self-judging replication (spec/self-judging-replication.md): does a model rank its own failing patches below its own
passing patches worse than it ranks other agents' patches, relative to outside judges?

Reads derived/selfpref_<tag>.jsonl for nine judges (reasoning-first score, temperature 0) on the 388 patches of the
50 SWE-bench Verified Mini issues. Output is one JSON object (keyed by self pair, plus "pooled") for log_wandb.py.

Usage: python3 self_judging_replication.py > derived/self_judging_replication_<date>.json
"""
import collections, json, os

import numpy as np
from scipy.stats import rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
FAMILY = {"gemma4-31b": "gemma", "gpt-oss-20b": "gpt-oss", "qwen35-9b": "qwen", "glm47-flash": "glm",
          "qwen3-coder": "qwen", "gpt-oss-120b": "gpt-oss", "glm-4.5": "glm", "kimi-k2": "kimi",
          "llama-4-maverick": "llama"}
JUDGES = list(FAMILY)
WRITER_FAMILY = {"gemma-4-31b": "gemma", "qwen3-coder": "qwen", "gpt-oss-120b": "gpt-oss", "glm-4.5": "glm",
                 "kimi-k2": "kimi", "llama-4-maverick": "llama", "devstral": "mistral"}
OWN = {"qwen3-coder": "qwen3-coder", "gpt-oss-120b": "gpt-oss-120b", "glm-4.5": "glm-4.5", "kimi-k2": "kimi-k2",
       "llama-4-maverick": "llama-4-maverick", "gemma4-31b": "gemma-4-31b"}  # judge tag -> writer it wrote as
NEW = ["qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2", "llama-4-maverick"]
B = 2000


def load():
    S, meta = collections.defaultdict(dict), {}
    for t in JUDGES:
        for l in open(os.path.join(HERE, "derived", f"selfpref_{t}.jsonl")):
            r = json.loads(l)
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], r["y"], r["writer"])
    pids = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    return pids, {p: S[p] for p in pids}, meta, len(S) - len(pids)


def auroc(score, y):
    """AUROC of -score for flagging failing (y=0) patches; ties count half."""
    pos = y == 0
    n1, n0 = pos.sum(), (~pos).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = rankdata(-score)
    return (r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def outside(j, w):
    return [k for k in JUDGES if k != j and FAMILY[k] != WRITER_FAMILY[w]]


def pair_measures(idx, X, y, wr, j, w):
    """Self drop, baseline drop and gap for judge j that wrote as w, on patch indices idx (may repeat)."""
    sw, yw = wr[idx], y[idx]
    own = idx[sw == w]
    rest = idx[sw != w]
    self_drop = auroc(X[j][rest], y[rest]) - auroc(X[j][own], y[own])
    drops = []
    for k in outside(j, w):
        rk = rest if k not in OWN else rest[wr[rest] != OWN[k]]
        drops.append(auroc(X[k][rk], y[rk]) - auroc(X[k][own], y[own]))
    base = float(np.mean(drops))
    return dict(self_auroc_own=auroc(X[j][own], y[own]), self_auroc_rest=auroc(X[j][rest], y[rest]),
                self_drop=self_drop, baseline_drop=base, gap=self_drop - base)


def leniency(idx, X, y, wr, j, w):
    """J minus outside judges' mean on failing patches: W's vs other writers'. Outside judges per patch exclude J and
    judges of the writer's family (W's family for W's patches, V's family for writer V's patches)."""
    def gaps(sel):
        out = []
        for i in sel:
            ks = [k for k in outside(j, w) if FAMILY[k] != WRITER_FAMILY[wr[i]]]
            out.append(X[j][i] - np.mean([X[k][i] for k in ks]))
        return np.array(out)
    fail = idx[y[idx] == 0]
    own, rest = fail[wr[fail] == w], fail[wr[fail] != w]
    a, b = gaps(own), gaps(rest)
    return dict(lenient_own_failing=a.mean(), lenient_other_failing=b.mean(), lenient_difference=a.mean() - b.mean(),
                share_ge95_own_failing=float((X[j][own] >= 95).mean()),
                share_ge95_other_failing=float((X[j][rest] >= 95).mean()))


def main():
    pids, S, meta, dropped = load()
    X = {t: np.array([S[p][t] for p in pids], float) for t in JUDGES}
    y = np.array([meta[p][1] for p in pids]); wr = np.array([meta[p][2] for p in pids])
    iss = np.array([meta[p][0] for p in pids]); issues = sorted(set(iss))
    by_issue = {i: np.where(iss == i)[0] for i in issues}
    allidx = np.arange(len(pids))
    pairs = NEW + ["gemma4-31b"]
    point = {j: pair_measures(allidx, X, y, wr, j, OWN[j]) for j in pairs}
    rng = np.random.default_rng(0)
    boot = collections.defaultdict(list)
    for _ in range(B):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        g = {j: pair_measures(idx, X, y, wr, j, OWN[j]) for j in pairs}
        for j in pairs:
            for m in ("self_drop", "baseline_drop", "gap"):
                boot[(j, m)].append(g[j][m])
        boot[("pooled", "gap")].append(np.nanmean([g[j]["gap"] for j in NEW]))
        boot[("pooled_with_gemma", "gap")].append(np.nanmean([g[j]["gap"] for j in pairs]))
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    out = {}
    for j in pairs:
        w = OWN[j]
        n = dict(own_failing=int(((wr == w) & (y == 0)).sum()), own_passing=int(((wr == w) & (y == 1)).sum()))
        res = {k: round(float(v), 3) for k, v in point[j].items()}
        res.update({f"{m}_ci95": ci(boot[(j, m)]) for m in ("self_drop", "baseline_drop", "gap")})
        res.update({k: round(float(v), 3) for k, v in leniency(allidx, X, y, wr, j, w).items()})
        res.update(n=n, outside_judges=outside(j, w), spec_role="primary pair" if j in NEW else "exploratory (not counted)")
        out[j] = res
    out["pooled"] = dict(gap=round(float(np.mean([point[j]["gap"] for j in NEW])), 3), gap_ci95=ci(boot[("pooled", "gap")]),
                         pairs=NEW, patches_rated_by_all=len(pids), patches_left_out=dropped,
                         gap_with_gemma=round(float(np.mean([point[j]["gap"] for j in pairs])), 3),
                         gap_with_gemma_ci95=ci(boot[("pooled_with_gemma", "gap")]))
    out["auroc_matrix"] = {t: {w: round(float(auroc(X[t][wr == w], y[wr == w])), 3) for w in WRITER_FAMILY} for t in JUDGES}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
