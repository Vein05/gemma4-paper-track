#!/usr/bin/env python3
"""Check D of spec/bug-token-precheck.md (addendum 2026-11-02): the 31B's own failing held-out patches, split by
whether any other writer's failing patch on the issue edits the same place (overlap >= 0.5, the 2026-10-28 method).
Leniency (judge minus outside judges' mean) of the local 31B, 12B and 26B-A4B in each group; 2,000 issue resamples.
Run from scripts/: python3 precheck/population_split.py > derived/population_split_2026-11-02.json"""
import collections, json, os, sys
sys.path.insert(0, os.getcwd())
SRC = os.path.join(os.getcwd(), "..", "notes", "idea-own-code-surprise-2026-10-28", "belief_check.py")
exec(open(SRC).read().split("own_of = ")[0])  # pids, X, y, wr, iss, text, sim, out_mean, W (12 judges)
import numpy as np
own_fail = [i for i in range(len(pids)) if wr[i] == W and y[i] == 0]
same = {}
for o in own_fail:
    others = [i for i in range(len(pids)) if iss[i] == iss[o] and wr[i] != W and y[i] == 0]
    same[o] = any(sim(text[pids[i]], text[pids[o]])["same_place"] >= 0.5 for i in others)
J = ["gemma4-31b-local", "gemma4-12b", "gemma4-26b-a4b", "gemma4-31b"]
D = {j: X[j] - out_mean for j in J}
groups = {"same place as another writer's failing patch": [o for o in own_fail if same[o]],
          "no other writer's failing patch at the same place": [o for o in own_fail if not same[o]]}
res = {g: dict(n=len(v), issues=len({iss[i] for i in v}),
               **{j: dict(leniency=round(float(D[j][v].mean()), 1), share_100=round(float(np.mean(X[j][v] == 100)), 3))
                  for j in J}) for g, v in groups.items()}
rng = np.random.default_rng(0)
v = groups["no other writer's failing patch at the same place"]
by = collections.defaultdict(list)
for i in v:
    by[iss[i]].append(i)
keys = sorted(by)
bs = {"local31b_minus_26b": [], "local31b_minus_12b": []}
for _ in range(2000):
    s = [i for k in rng.choice(keys, len(keys)) for i in by[k]]
    bs["local31b_minus_26b"].append(D["gemma4-31b-local"][s].mean() - D["gemma4-26b-a4b"][s].mean())
    bs["local31b_minus_12b"].append(D["gemma4-31b-local"][s].mean() - D["gemma4-12b"][s].mean())
res["no_same_place_contrasts"] = {k: dict(point=round(float(np.mean(D["gemma4-31b-local"][v]) - np.mean(D[k.split("_minus_")[1].replace("26b", "gemma4-26b-a4b").replace("12b", "gemma4-12b")][v])), 1),
                                          ci=[round(float(np.percentile(b, 2.5)), 1), round(float(np.percentile(b, 97.5)), 1)])
                                  for k, b in bs.items()}
print(json.dumps(res, indent=1))
