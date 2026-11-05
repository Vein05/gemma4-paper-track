#!/usr/bin/env python3
"""Rubber-stamping check with a free local judge (spec/open-panel-check.md, written before the Lite and LiveCodeBench
Qwen3-32B scores existed).

Leniency of judge k = mean over own failing patches of E minus mean over other writers' failing patches of E, where
E = k's score minus the panel's mean on the same patch (panel judges of the writer's family dropped; a patch with no
panel judge left is dropped). Pooled over patches as in per_writer_leniency.py. 2,000 issue resamples, seed 0.

Usage (from scripts/): python3 open_panel_check.py > derived/open_panel_check_2026-11-03.json
"""
import collections, json, os, sys

import numpy as np
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fresh_judging  # noqa: E402
from fresh_judging import OWN, WRITER_FAMILY, load  # noqa: E402
from per_writer_leniency import G, GW, J6, J7, J9, LCB_WRITERS, LITE_WRITERS, load_rows  # noqa: E402

Q = "qwen3-32b-local"
fresh_judging.FAMILY[Q] = "qwen"
FAMILY = fresh_judging.FAMILY
OPEN4 = [Q, "gpt-oss-20b", "qwen35-9b", "glm47-flash"]
ROOT = os.path.join(HERE, "..")
LITE = os.path.join(ROOT, "data", "public", "third-party-lite", "patches.jsonl")
LCB = os.path.join(ROOT, "data", "livecodebench-pilot", "judging", "programs.jsonl")


def excess(X, wr, wfam, k, panel):
    out = np.full(len(wr), np.nan)
    for i in range(len(wr)):
        p = [X[m][i] for m in panel if m != k and m != G and FAMILY[m] != wfam.get(wr[i])]
        if p:
            out[i] = X[k][i] - np.mean(p)
    return out


def leniency_boot(E, y, wr, iss, own_writer):
    fail = (y == 0) & ~np.isnan(E)
    own, oth = fail & (wr == own_writer), fail & (wr != own_writer)
    if not own.any() or not oth.any():
        return None
    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    f = lambda idx: E[idx][own[idx]].mean() - E[idx][oth[idx]].mean()
    rng = np.random.default_rng(0); B = []
    for _ in range(2000):
        idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        if own[idx].any() and oth[idx].any():
            B.append(f(idx))
    return dict(value=round(float(f(np.arange(len(y)))), 1),
                ci95=[round(float(np.percentile(B, 2.5)), 1), round(float(np.percentile(B, 97.5)), 1)],
                own_failing=int(own.sum()), other_failing=int(oth.sum()))


def flagged(r):
    return r is not None and r["ci95"][0] > 0


def sample_size(E, y, wr, iss, own_writer, ks=(10, 20, 30, 50, 80), draws=1000, inner=500, seed=0):
    """Share of draws (issues taken in random order until k own failing patches) in which the bootstrap interval of
    the leniency is above 0."""
    fail = (y == 0) & ~np.isnan(E)
    own, oth = fail & (wr == own_writer), fail & (wr != own_writer)
    issues = sorted(set(iss))
    agg = {i: (E[(iss == i) & own].sum(), int(((iss == i) & own).sum()),
               E[(iss == i) & oth].sum(), int(((iss == i) & oth).sum())) for i in issues}
    A = np.array([agg[i] for i in issues], float)
    rng = np.random.default_rng(seed); out = {}
    for k in ks:
        if A[:, 1].sum() < k:
            out[str(k)] = None; continue
        hits = 0
        for _ in range(draws):
            order = rng.permutation(len(issues)); c = np.cumsum(A[order, 1])
            sel = A[order[: int(np.searchsorted(c, k)) + 1]]
            W = rng.multinomial(len(sel), np.ones(len(sel)) / len(sel), size=inner)
            S = W @ sel
            with np.errstate(invalid="ignore", divide="ignore"):
                L = S[:, 0] / S[:, 1] - S[:, 2] / S[:, 3]
            L = L[~np.isnan(L)]
            hits += len(L) > 0 and np.percentile(L, 2.5) > 0
        out[str(k)] = round(hits / draws, 3)
    return out


def reviewer(X, y, wr, iss, rev):
    own = wr == GW
    yo, iso = y[own], iss[own]; a, b = X[rev][own], X[G][own]
    issues = sorted(set(iso)); by = {i: np.where(iso == i)[0] for i in issues}
    rng = np.random.default_rng(0); B = []
    for _ in range(2000):
        idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        if len(set(yo[idx])) == 2:
            B.append(roc_auc_score(yo[idx], a[idx]) - roc_auc_score(yo[idx], b[idx]))

    def topq(s):
        n = max(1, int(round(len(s) / 4))); r = np.random.default_rng(1); v = []
        for _ in range(200):
            order = np.lexsort((r.random(len(s)), -s))
            v.append(yo[order[:n]].mean())
        return round(float(np.mean(v)), 3)

    return dict(own_patches=int(own.sum()), own_pass_rate=round(float(yo.mean()), 3),
                auroc_reviewer=round(float(roc_auc_score(yo, a)), 3), auroc_gemma=round(float(roc_auc_score(yo, b)), 3),
                diff=round(float(roc_auc_score(yo, a) - roc_auc_score(yo, b)), 3),
                diff_ci95=[round(float(np.percentile(B, 2.5)), 3), round(float(np.percentile(B, 97.5)), 3)],
                top_quarter_pass_reviewer=topq(a), top_quarter_pass_gemma=topq(b))


def one_set(X, y, wr, iss, wfam, paid, self_judges):
    res = {"patches": int(len(y))}
    for name, panel in [("qwen3-32b_alone", [Q]), ("open4", OPEN4), ("paid_panel", paid)]:
        E = excess(X, wr, wfam, G, panel)
        res[f"gemma_{name}"] = leniency_boot(E, y, wr, iss, GW)
    E = excess(X, wr, wfam, G, [Q])
    res["patches_needed_qwen_alone"] = sample_size(E, y, wr, iss, GW)
    res["self_judges_qwen_alone"] = {}
    for k in self_judges:
        Ek = excess(X, wr, wfam, k, [Q])
        r = leniency_boot(Ek, y, wr, iss, OWN[k])
        res["self_judges_qwen_alone"][k] = r if r else "not computable (own patches share the panel's family)"
        if r:
            res.setdefault("false_flag_patches_needed", {})[k] = sample_size(Ek, y, wr, iss, OWN[k])
    res["reviewer_qwen3-32b"] = reviewer(X, y, wr, iss, Q)
    return res


def main():
    out = {}
    pids, X, y, wr, iss, _ = load(J9 + [Q], ["main-a", "main-b"])
    others = [k for k in OWN if k != G and k in J9]
    out["held-out"] = one_set(X, y, wr, iss, WRITER_FAMILY, J9, others)
    for name, items, prefix, J, wfam in [("swe-bench-lite", LITE, "lite", J7, LITE_WRITERS),
                                         ("livecodebench", LCB, "lcb", J6, LCB_WRITERS)]:
        if not os.path.exists(os.path.join(HERE, "derived", f"{prefix}_{Q}.jsonl")):
            out[name] = "Qwen3-32B scores not yet available"; continue
        X, y, wr, iss = load_rows(items, prefix, J + [Q])
        out[name] = one_set(X, y, wr, iss, wfam, J, [])
    sets = [s for s in ("held-out", "swe-bench-lite", "livecodebench") if isinstance(out[s], dict)]
    if len(sets) == 3:
        works = all(flagged(out[s]["gemma_qwen3-32b_alone"]) for s in sets) and not any(
            isinstance(v, dict) and flagged(v) for v in out["held-out"]["self_judges_qwen_alone"].values())
        out["reading_check"] = "check works with one free judge" if works else "check needs a larger panel"
        ks = ["10", "20", "30", "50", "80"]
        need = next((k for k in ks if all((out[s]["patches_needed_qwen_alone"].get(k) or 0) >= 0.8 for s in sets)), None)
        out["reading_patches_needed"] = need
        rv = all(out[s]["reviewer_qwen3-32b"]["diff_ci95"][0] > 0 for s in ("held-out", "swe-bench-lite"))
        out["reading_reviewer"] = "local reviewer helps" if rv else "not offered as a method"
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
