#!/usr/bin/env python3
"""Per-writer leniency and a placebo check, on the held-out issues, SWE-bench Lite and LiveCodeBench (exploratory,
chosen on 2026-11-01 after the results of spec/third-party-lite.md and spec/livecodebench-judging.md were seen).

Leniency of a judge on an item = its score minus the mean score of the panel on that item. The panel is every other
judge except Gemma and except judges of the writer's family (for Gemma as judge: the paper's outside judges).

1. Per writer: Gemma's leniency and share of 100s on each writer's failing items, the writer's pass rate, and
   Gemma's own-minus-that-writer leniency difference with a 95% interval.
2. Placebo: each judge treated as if it wrote Gemma's items: its leniency on Gemma's failing items minus on other
   writers' failing items. Gemma's value is the paper's leniency measure. Also Gemma minus the largest of the others
   (the maximum taken inside each resample).
Intervals: 2,000 bootstrap resamples of issues (problems), seed 0.

Usage: python3 per_writer_leniency.py > derived/per_writer_leniency_2026-11-01.json
"""
import collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fresh_judging import FAMILY, WRITER_FAMILY, load  # noqa: E402

G, GW = "gemma4-31b", "gemma-4-31b"
LITE_WRITERS = {"gemma-4-31b": "gemma", "deepseek-v3": None, "swe-fixer-qwen2.5-72b": "qwen",
                "entropo-qwen3-coder-30b": "qwen", "claude-4-sonnet": None}
LCB_WRITERS = {"gemma-4-31b": "gemma", "deepseek-v3": None, "claude-3.5-sonnet": None}
J9 = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
      "llama-4-maverick"]
J7 = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "llama-4-maverick"]
J6 = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "gpt-oss-120b", "llama-4-maverick"]


def load_rows(items, prefix, judges):
    P = {r["pid"]: r for r in map(json.loads, open(items))}
    S = collections.defaultdict(dict)
    for t in judges:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"{prefix}_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in S.items() if len(s) == len(judges))
    y = np.array([P[p]["y"] for p in pids]); wr = np.array([P[p]["writer"] for p in pids])
    iss = np.array([P[p]["iid"] for p in pids])
    X = {t: np.array([S[p][t] for p in pids], float) for t in judges}
    return X, y, wr, iss


def analyse(X, y, wr, iss, judges, wfam):
    n = len(y)
    D = {}
    for k in judges:
        excl = {k} if k == G else {k, G}
        D[k] = np.array([X[k][i] - np.mean([X[m][i] for m in judges if m not in excl and FAMILY[m] != wfam[wr[i]]])
                         for i in range(n)])
    fail = y == 0
    writers = sorted(set(wr))

    def placebo(idx, k):
        f = idx[fail[idx]]
        return D[k][f[wr[f] == GW]].mean() - D[k][f[wr[f] != GW]].mean()

    def own_minus(idx, v):
        f = idx[fail[idx]]
        return D[G][f[wr[f] == GW]].mean() - D[G][f[wr[f] == v]].mean()

    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); B = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        pl = {k: placebo(idx, k) for k in judges}
        for k in judges:
            B["placebo", k].append(pl[k])
        B["gemma_minus_max_other"].append(pl[G] - max(pl[k] for k in judges if k != G))
        for v in writers:
            if v != GW:
                B["own_minus", v].append(own_minus(idx, v))
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 1), round(float(np.nanpercentile(v, 97.5)), 1)]
    allidx = np.arange(n)
    out = {"items": n, "per_writer": {}, "placebo": {}}
    for v in writers:
        m = fail & (wr == v)
        row = dict(failing=int(m.sum()), pass_rate=round(float(y[wr == v].mean()), 3),
                   gemma_leniency_failing=round(float(D[G][m].mean()), 1),
                   gemma_scored100_failing=int((X[G][m] == 100).sum()),
                   gemma_scored100_failing_share=round(float((X[G][m] == 100).mean()), 3))
        if v != GW:
            row["own_minus_this_writer"] = round(float(own_minus(allidx, v)), 1)
            row["own_minus_this_writer_ci95"] = ci(B["own_minus", v])
        out["per_writer"][v] = row
    for k in judges:
        out["placebo"][k] = dict(value=round(float(placebo(allidx, k)), 1), ci95=ci(B["placebo", k]),
                                 scored100_gemma_failing=round(float((X[k][fail & (wr == GW)] == 100).mean()), 3),
                                 scored100_other_failing=round(float((X[k][fail & (wr != GW)] == 100).mean()), 3))
    pl = {k: placebo(allidx, k) for k in judges}
    out["gemma_minus_max_other"] = round(float(pl[G] - max(pl[k] for k in judges if k != G)), 1)
    out["gemma_minus_max_other_ci95"] = ci(B["gemma_minus_max_other"])
    return out


def main():
    res = {}
    pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
    res["held-out"] = analyse(X, y, wr, iss, J9, WRITER_FAMILY)
    X, y, wr, iss = load_rows(os.path.join(HERE, "..", "data", "public", "third-party-lite", "patches.jsonl"), "lite", J7)
    res["swe-bench-lite"] = analyse(X, y, wr, iss, J7, LITE_WRITERS)
    X, y, wr, iss = load_rows(os.path.join(HERE, "..", "data", "livecodebench-pilot", "judging", "programs.jsonl"), "lcb", J6)
    res["livecodebench"] = analyse(X, y, wr, iss, J6, LCB_WRITERS)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
