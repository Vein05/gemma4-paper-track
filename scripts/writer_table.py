#!/usr/bin/env python3
"""Gemma 4 31B's scores on failing held-out patches, by writer (exploratory, chosen 2026-11-07 after the results).

For each writer: the share of issues it solves among the patches all nine judges scored, its number of failing
patches, the share of those that Gemma scores 100, and Gemma's mean score minus the mean of the outside judges (the
eight judges from other model families than Gemma) on them. Also how often Gemma's score on a failing patch is 100 or
below 50, over all six writers. One JSON object on stdout.

Usage: python3 writer_table.py > derived/writer_table_2026-11-07.json
"""
import json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fresh_judging import FAMILY, load  # noqa: E402

J9 = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
      "llama-4-maverick"]
G = "gemma4-31b"

pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
outside = np.mean([X[k] for k in J9 if FAMILY[k] != FAMILY[G]], 0)
g, fail = X[G], y == 0
rows = {}
for w in sorted(set(wr)):
    m, f = wr == w, (wr == w) & fail
    rows[w] = dict(patches=int(m.sum()), solved=round(float(y[m].mean()), 3), failing=int(f.sum()),
                   gemma_100=round(float(np.mean(g[f] == 100)), 3),
                   above_outside=round(float(np.mean(g[f] - outside[f])), 1))
print(json.dumps(dict(
    judges=J9, outside_judges=[k for k in J9 if FAMILY[k] != FAMILY[G]], per_writer=rows,
    failing_all_writers=dict(n=int(fail.sum()), gemma_100=round(float(np.mean(g[fail] == 100)), 3),
                             gemma_below_50=round(float(np.mean(g[fail] < 50)), 3),
                             gemma_100_or_below_50=round(float(np.mean((g[fail] == 100) | (g[fail] < 50))), 3))),
    indent=1))
