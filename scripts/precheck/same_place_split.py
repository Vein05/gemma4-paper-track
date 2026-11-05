#!/usr/bin/env python3
"""Check 1 of spec/bug-token-precheck.md: the 31B's 100s on other writers' same-place failing patches, split by the
blind coder's label (same change vs different change as the 31B's failing patch on the issue).

Inputs: derived/same_place_pairs_2026-11-02.jsonl, derived/same_place_pairs_key_2026-11-02.json,
../data/hand-codes/same-place-pairs-labels.csv. Run from scripts/:
  python3 precheck/same_place_split.py > derived/same_place_split_2026-11-02.json"""
import collections, csv, json, os, re, sys
sys.path.insert(0, os.getcwd())
import numpy as np
import fresh_judging as fj

NINE = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
        "llama-4-maverick"]
G = ["gemma4-31b-local", "gemma4-31b"]
fj.FAMILY.update({"gemma4-31b-local": "gemma"})
pids, X, y, wr, iss, S = fj.load(NINE + ["gemma4-31b-local"], ["main-a", "main-b"])
outside = [k for k in NINE if fj.FAMILY[k] != "gemma"]
om = np.array([np.mean([X[k][i] for k in outside if fj.FAMILY[k] != fj.WRITER_FAMILY[wr[i]]]) for i in range(len(pids))])
ix = {p: i for i, p in enumerate(pids)}

pairs = [json.loads(l) for l in open("derived/same_place_pairs_2026-11-02.jsonl")]
key = {k["pair"]: k for k in json.load(open("derived/same_place_pairs_key_2026-11-02.json"))}
lab = {int(r["pair"]): r for r in csv.DictReader(open("../data/hand-codes/same-place-pairs-labels.csv"))}
assert len(lab) == len(pairs) == 58


def toks(t):
    out = set()
    for l in t.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            s = re.sub(r"#.*", "", l[1:]).strip()
            if s:
                out |= set(s.split())
    return out


groups = collections.defaultdict(list)
jac = []
for n, p in enumerate(pairs, 1):
    assert key[n]["other_pid"] == p["other_pid"]
    groups[lab[n]["change"]].append(ix[p["other_pid"]])
    groups[f"shares_wrong_part={lab[n]['shares_wrong_part']}"].append(ix[p["other_pid"]])
    a, b = toks(p["own_patch"]), toks(p["other_patch"])
    jac.append((lab[n]["change"], len(a & b) / len(a | b) if a | b else 1.0))
own_fail_issues = {p["iid"] for p in pairs}
groups["own failing, same 29 issues"] = [i for i in range(len(pids)) if wr[i] == "gemma-4-31b" and y[i] == 0
                                         and iss[i] in own_fail_issues]
groups["own failing, all"] = [i for i in range(len(pids)) if wr[i] == "gemma-4-31b" and y[i] == 0]


def stats(idx):
    idx = np.array(idx)
    return {j: dict(share_100=float(np.mean(X[j][idx] == 100)), leniency=float(np.mean(X[j][idx] - om[idx])))
            for j in G}


res = {"n": {g: len(v) for g, v in groups.items()}, "point": {g: stats(v) for g, v in groups.items()}}
# bootstrap by issue: same minus different, share of 100s and leniency
rng = np.random.default_rng(0)
issues = sorted(own_fail_issues)
by = collections.defaultdict(lambda: collections.defaultdict(list))
for g in ("same", "different"):
    for i in groups[g]:
        by[iss[i]][g].append(i)
boot = {j: {"share_100": [], "leniency": []} for j in G}
for _ in range(2000):
    smp = rng.choice(issues, len(issues))
    s = [i for v in smp for i in by[v]["same"]]; d = [i for v in smp for i in by[v]["different"]]
    if not s or not d:
        continue
    for j in G:
        boot[j]["share_100"].append(np.mean(X[j][s] == 100) - np.mean(X[j][d] == 100))
        boot[j]["leniency"].append(np.mean(X[j][s] - om[s]) - np.mean(X[j][d] - om[d]))
res["same_minus_different"] = {j: {m: dict(point=res["point"]["same"][j][m] - res["point"]["different"][j][m],
                                            ci=[float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))])
                                    for m, v in boot[j].items()} for j in G} if groups["same"] and groups["different"] else None
res["added_token_jaccard_median"] = {g: float(np.median([v for c, v in jac if c == g])) for g in ("same", "different")
                                     if any(c == g for c, _ in jac)}
print(json.dumps(res, indent=1))
