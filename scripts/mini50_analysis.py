#!/usr/bin/env python3
"""Gemma 4's own-patch check on the 50 Mini issues with its mini-SWE-agent patches (spec/mini50-same-harness.md).

Gemma's new patches (runs/mini50) are scored in derived/fresh_<tag>.jsonl; the control writers' patches on the same
issues keep their scores from the original study (derived/selfpref_<tag>.jsonl). The gap, self drop and baseline drop
are self_judging_replication.pair_measures, 95% interval from 2,000 issue resamples (seed 0). Secondary: rubber-stamp
rate (scored 100) on Gemma's own failing patches, new and original. Also the original study's Gemma gap through the
same code, and (exploratory, not in the spec) the gap with Gemma patches that needed a re-ask left out.

Usage: python3 mini50_analysis.py [--drop django__django-11848] [--timeout-fails] > derived/mini50_<date>.json
"""
import argparse, collections, json, os

import numpy as np

from fresh_judging import HERE, RUNS, labels
from self_judging_replication import JUDGES, auroc, leniency, pair_measures

W, J = "gemma-4-31b", "gemma4-31b"


def rows(path):
    return [json.loads(l) for l in open(path)]


def build(drop, timeout_fails):
    mini = {json.loads(l)["instance_id"] for l in open(os.path.join(RUNS, "mini50", "preds.jsonl"))}
    lab = labels(["mini50"])
    if timeout_fails:  # SWE-bench counts a test timeout as unresolved; labels() leaves timeouts out
        lab.update({x["instance_id"]: 0 for x in rows(os.path.join(RUNS, "mini50", "labels.jsonl"))
                    if x["status"] == "timeout"})
    lab = {i: y for i, y in lab.items() if i not in drop}
    S, meta, reasked = collections.defaultdict(dict), {}, set()
    orig = collections.defaultdict(dict)
    for t in JUDGES:
        seen = collections.Counter()
        for r in rows(os.path.join(HERE, "derived", f"fresh_{t}.jsonl")):
            if r["iid"] in mini and r["writer"] == W:
                seen[r["pid"]] += 1
                if r.get("err") is None and r.get("parsed") is not None and r["iid"] in lab:
                    S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], lab[r["iid"]], W)
        reasked |= {p for p, n in seen.items() if n > 1}
        for r in rows(os.path.join(HERE, "derived", f"selfpref_{t}.jsonl")):
            if r.get("err") is None and r.get("parsed") is not None:
                orig[r["pid"]][t] = r["parsed"]
                if r["writer"] != W:  # control writers' patches, original scores
                    S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], int(r["y"]), r["writer"])
                else:
                    meta.setdefault(("orig", r["pid"]), (r["iid"], int(r["y"]), W))
    return S, meta, orig, reasked


def arrays(S, meta, pids, key=lambda p: p):
    X = {t: np.array([S[p][t] for p in pids], float) for t in JUDGES}
    y = np.array([meta[key(p)][1] for p in pids]); wr = np.array([meta[key(p)][2] for p in pids])
    return X, y, wr, np.array([meta[key(p)][0] for p in pids])


def gap(X, y, wr, iss):
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    allidx = np.arange(len(y))
    point = pair_measures(allidx, X, y, wr, J, W)
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        m = pair_measures(idx, X, y, wr, J, W)
        for k in ("self_drop", "baseline_drop", "gap"):
            boot[k].append(m[k])
        boot["lenient_difference"].append(leniency(idx, X, y, wr, J, W)["lenient_difference"])
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    out = {k: round(float(v), 3) for k, v in point.items()}
    out.update({f"{k}_ci95": ci(v) for k, v in boot.items()})
    out.update({k: round(float(v), 3) for k, v in leniency(allidx, X, y, wr, J, W).items()})
    own_fail = (wr == W) & (y == 0)
    out["scored100_own_failing"] = round(float((X[J][own_fail] == 100).mean()), 3)
    out["scored100_control_failing"] = round(float((X[J][(wr != W) & (y == 0)] == 100).mean()), 3)
    out["scored100_own_failing_count"] = int((X[J][own_fail] == 100).sum())
    out["n"] = dict(issues=len(issues), own_failing=int(own_fail.sum()), own_passing=int(((wr == W) & (y == 1)).sum()),
                    control_failing=int(((wr != W) & (y == 0)).sum()), control_passing=int(((wr != W) & (y == 1)).sum()))
    out["auroc_by_judge_own"] = {t: round(float(auroc(X[t][wr == W], y[wr == W])), 3) for t in JUDGES}
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--drop", default="")
    ap.add_argument("--timeout-fails", action="store_true")
    a = ap.parse_args()
    drop = set(filter(None, a.drop.split(",")))
    S, meta, orig, reasked = build(drop, a.timeout_fails)
    full = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    new_gemma = [p for p in full if meta[p][2] == W]
    res = dict(dropped_issues=sorted(drop), timeout_counted_failing=a.timeout_fails, new_gemma_patches_rated_by_all=len(new_gemma),
               new_gemma_patches_left_out=sum(1 for p, s in S.items() if meta[p][2] == W and len(s) < len(JUDGES)))
    res["primary"] = gap(*arrays(S, meta, full))
    keep = [p for p in full if p not in reasked]
    res["exploratory_reasked_gemma_patches_left_out"] = dict(left_out=len(full) - len(keep), **gap(*arrays(S, meta, keep)))
    opids = sorted(p for p, s in orig.items() if len(s) == len(JUDGES))
    key = lambda p: ("orig", p) if ("orig", p) in meta else p
    res["original_study_same_code"] = gap(*arrays(orig, meta, opids, key))
    print(json.dumps({J: res}, indent=1))


if __name__ == "__main__":
    main()
