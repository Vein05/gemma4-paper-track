#!/usr/bin/env python3
"""What Gemma 4 writes when it scores its own failing held-out patch 100 and outside judges score it low
(exploratory: the case rule was set after a first look at the answers, 2026-10-22,
notes/human-interest-2026-10-22/README.md). No model calls.

Cases: Gemma's own failing patches on the held-out issues, scored by all nine judges, that Gemma scored 100 and at
least two outside judges scored 50 or less. Two coders code each case on their own from CODEBOOK, one row per case
in data/hand-codes/rubber-stamp-coder-<a|b>.csv (columns pid, code, opposite).

Usage:
  python3 rubber_stamp_reasons.py packet > ../data/hand-codes/rubber-stamp-cases.md
  python3 rubber_stamp_reasons.py agree > derived/rubber_stamp_reasons_2026-10-22.json
"""
import csv, json, os, sys

import numpy as np

from fresh_judging import RUNS, load, pid_of, strip_tests

HERE = os.path.dirname(os.path.abspath(__file__))
CODES = os.path.join(HERE, "..", "data", "hand-codes")
JUDGES = "gemma4-31b,glm-4.5,glm47-flash,gpt-oss-120b,gpt-oss-20b,kimi-k2,llama-4-maverick,qwen3-coder,qwen35-9b".split(",")
G, GW, LOW = "gemma4-31b", "gemma-4-31b", 50
CODEBOOK = """For each case, read the outside judges' answers first and find the main defect: the problem the
low-scoring outside judges give as the reason for their low score (if they give several, the one most of them
name). Then read Gemma's answer.

- code = named: Gemma's answer names that same defect or risk (the same specific problem, even if Gemma calls it
  minor, acceptable or consistent with the issue) and still scores 100.
- code = not_named: Gemma's answer never mentions that defect.
- opposite = 1: Gemma's answer states the opposite of the outside judges' specific claim (for example, it calls a
  keyword correct that they call wrong). Otherwise 0. Only a not_named case can have opposite = 1."""


def cases():
    pids, X, y, wr, iss, _ = load(JUDGES, ["main-a", "main-b"])
    outs = [t for t in JUDGES if t != G]
    keep = [i for i in range(len(pids)) if wr[i] == GW and y[i] == 0 and X[G][i] == 100
            and sum(X[t][i] <= LOW for t in outs) >= 2]
    n_own_fail_100 = int(((wr == GW) & (y == 0) & (X[G] == 100)).sum())
    return [pids[i] for i in keep], {pids[i]: {t: X[t][i] for t in JUDGES} for i in keep}, n_own_fail_100


def answers(pids):
    """Last parsed answer per judge (re-asks supersede), as in fresh_judging.load."""
    A = {p: {} for p in pids}
    for t in JUDGES:
        for l in open(os.path.join(HERE, "derived", f"fresh_{t}.jsonl")):
            r = json.loads(l)
            if r["pid"] in A and r.get("err") is None and r.get("parsed") is not None:
                A[r["pid"]][t] = r["content"]
    return A


def gemma_patches():
    out = {}
    for r in ("main-a", "main-b"):
        for l in open(os.path.join(RUNS, r, "preds.jsonl")):
            x = json.loads(l)
            p = strip_tests(x["model_patch"] or "")
            out[pid_of(x["instance_id"], GW, p)] = p
    return out


def packet():
    pids, S, n = cases()
    A, P = answers(pids), gemma_patches()
    print(f"# Rubber-stamped failing patches: {len(pids)} cases\n")
    print(f"Gemma 4 31B's own failing patches on the held-out issues that Gemma scored 100 and at least two outside "
          f"judges scored {LOW} or less ({len(pids)} of the {n} own failing patches Gemma scored 100). Every patch "
          f"fails the issue's hidden tests.\n\n## Codebook\n\n{CODEBOOK}\n")
    for k, p in enumerate(pids, 1):
        low = sorted((t for t in JUDGES if t != G and S[p][t] <= LOW), key=lambda t: S[p][t])
        print(f"\n---\n\n## Case {k}: `{p}`\n\nScores: " + ", ".join(f"{t} {S[p][t]:.0f}" for t in JUDGES) + "\n")
        print(f"### Patch (tests removed)\n\n```diff\n{P[p][:6000]}\n```\n")
        for t in low:
            print(f"### Outside judge {t} (score {S[p][t]:.0f})\n\n{A[p][t].strip()}\n")
        print(f"### Gemma 4 31B (score 100)\n\n{A[p][G].strip()}\n")


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    po = float((a == b).mean())
    pe = sum(float((a == c).mean()) * float((b == c).mean()) for c in set(a) | set(b))
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def read(name):
    return {r["pid"]: r for r in csv.DictReader(open(os.path.join(CODES, f"rubber-stamp-coder-{name}.csv")))}


def agree():
    pids, _, n = cases()
    C = {c: read(c) for c in ("a", "b")}
    for c, r in C.items():  # coded before 2026-11-09, when 2 of the 31 coded patches were regraded as passing
        assert set(pids) <= set(r), f"coder {c} misses {sorted(set(pids) - set(r))}"
    rng = np.random.default_rng(0)
    out = dict(rule=f"own failing held-out patch, Gemma 100, at least two outside judges <= {LOW}",
               own_failing_scored_100=n, cases=len(pids))
    for field in ("code", "opposite"):
        a, b = [C["a"][p][field] for p in pids], [C["b"][p][field] for p in pids]
        out[field] = dict(agreement=round(float(np.mean([x == y for x, y in zip(a, b)])), 3), kappa=kappa(a, b))
    for c in ("a", "b"):
        named = np.array([C[c][p]["code"] == "named" for p in pids])
        v = rng.binomial(len(pids), named.mean(), 20000) / len(pids)
        out[f"coder_{c}"] = dict(named=int(named.sum()), not_named=int((~named).sum()),
                                 opposite=int(sum(C[c][p]["opposite"] == "1" for p in pids)),
                                 named_share=round(float(named.mean()), 3),
                                 named_share_ci95=[round(float(x), 3) for x in np.percentile(v, [2.5, 97.5])])
    both = [p for p in pids if C["a"][p]["code"] == C["b"][p]["code"] == "named"]
    either = [p for p in pids if "named" in (C["a"][p]["code"], C["b"][p]["code"])]
    out["named_by_both"], out["named_by_either"] = len(both), len(either)
    out["disagreements"] = [p for p in pids if C["a"][p]["code"] != C["b"][p]["code"]]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"packet": packet, "agree": agree}[sys.argv[1]]()
