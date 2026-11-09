#!/usr/bin/env python3
"""Exploratory checks on the equally-strong-writers run (not in spec/matched-writers.md; chosen on 2026-11-09 after
its result was read). Same patches, judges, family weighting and resampling as `matched_writers.py analyze`.

1. Split of the planned gap: Gemma's own mean score, and the outside judges' mean score, on Gemma's own failing
   patches minus on the equally strong writers' failing patches.
2. The planned gap with one outside panel for every writer: the three judges of no writer's family, and all eight
   other judges.

Usage: python3 matched_writers_split.py > derived/matched_writers_split_2026-11-09.json
"""
import collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fresh_judging import FAMILY  # noqa: E402
from matched_writers import PATCHES, family_of, scores  # noqa: E402
from per_writer_leniency import G, GW, J9  # noqa: E402


def main():
    meta = {r["pid"]: r for r in map(json.loads, open(PATCHES))}
    S, _ = scores("matched", meta)
    pids = sorted(p for p in meta if len(S[p]) == len(J9))
    wr = np.array([meta[p]["writer"] for p in pids]); iss = np.array([meta[p]["iid"] for p in pids])
    fam = [meta[p]["family"] for p in pids]
    Xg = np.array([S[p][G] for p in pids], float)
    panel = lambda judges_of: np.array([np.mean([S[p][m] for m in judges_of(i)]) for i, p in enumerate(pids)])
    outside = panel(lambda i: [m for m in J9 if m != G and FAMILY[m] != fam[i]])
    neutral = [m for m in J9 if FAMILY[m] in ("qwen", "llama")]
    writers = sorted(set(wr) - {GW}); families = sorted({family_of(w) for w in writers})

    def own_minus_balanced(v, idx):
        w, x = wr[idx], v[idx]
        wm = {k: (x[w == k].mean() if (w == k).any() else np.nan) for k in writers}
        oth = np.nanmean([np.nanmean([wm[k] for k in writers if family_of(k) == f]) for f in families])
        own = x[w == GW].mean() if (w == GW).any() else np.nan
        return own, oth

    series = {"gemma_score": Xg, "outside_score": outside,
              "extra_trust_three_judges_of_no_writers_family": Xg - panel(lambda i: neutral),
              "extra_trust_all_eight_other_judges": Xg - panel(lambda i: [m for m in J9 if m != G])}
    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); B = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        for k, v in series.items():
            o, t = own_minus_balanced(v, idx); B[k].append(o - t)
    res = {}
    for k, v in series.items():
        o, t = own_minus_balanced(v, np.arange(len(pids)))
        res[k] = dict(own=round(float(o), 1), equally_strong_family_balanced=round(float(t), 1),
                      difference=round(float(o - t), 1),
                      ci95=[round(float(np.nanpercentile(B[k], q)), 1) for q in (2.5, 97.5)])
    res.update(exploratory=True, patches=len(pids), issues=len(issues), judges_of_no_writers_family=neutral)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
