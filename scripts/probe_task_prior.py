#!/usr/bin/env python3
"""How much of `resolved` is explained by task identity alone?

(1) Intraclass correlation of `resolved` across repeated runs of the same task (GraphLoc-129 run table, public Kaggle dataset
    zzgtylors/graphloc-129-localization-labels-and-agent-runs, Apache-2.0: 3 runs x 2 agent configs x 106 tasks).
(2) AUROC, on the 76 labelled rishav traces, of a predictor that uses ONLY other agents' mean resolve rate on the same task.
Usage: python3 probe_task_prior.py <e2e_runs.csv> derived/features_rishav.csv derived/task_sound_flags_dmitriigluzdov.csv
"""
import sys
import numpy as np
import pandas as pd
from probe_baselines import auroc, cluster_boot

g = pd.read_csv(sys.argv[1])
for arm, d in g.groupby("arm"):
    p = d.pivot_table(index="instance_id", columns="run", values="resolved").dropna()
    x = p.values; n, k = x.shape
    msb = k * np.var(x.mean(1), ddof=1); msw = ((x - x.mean(1, keepdims=True)) ** 2).sum() / (n * (k - 1))
    icc = (msb - msw) / (msb + (k - 1) * msw)
    print(f"arm {arm}: {n} tasks x {k} runs, mean resolved {x.mean():.3f}, ICC(1) {icc:.3f}, tasks solved 0/1/2/3 of 3: {np.bincount(x.sum(1).astype(int), minlength=k+1).tolist()}")

prior = g.groupby("instance_id").resolved.mean().rename("prior_other_agents")
d = pd.read_csv(sys.argv[2]).merge(pd.read_csv(sys.argv[3]), on="task_id").merge(prior, left_on="task_id", right_index=True, how="left")
rows = []
for name, x in [("rishav traces with a prior", d[d.prior_other_agents.notna()]),
                ("... sound, non-empty patch", d[d.prior_other_agents.notna() & (d.sound == 1) & (d.patch_nonempty == 1)])]:
    a = auroc(x.resolved, x.prior_other_agents); lo, hi = cluster_boot(x, "prior_other_agents")
    rows.append(dict(set=name, n=len(x), n_pos=int(x.resolved.sum()), auroc=round(a, 3), ci_lo=round(lo, 3), ci_hi=round(hi, 3)))
r = pd.DataFrame(rows); print(r.to_string(index=False))
r.to_csv("derived/auroc_task_prior.csv", index=False)
print("rishav traces without a prior (task not in the GraphLoc run table):", int(d.prior_other_agents.isna().sum()),
      "resolved among them:", int(d[d.prior_other_agents.isna()].resolved.sum()))
