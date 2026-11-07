#!/usr/bin/env python3
"""Skip the repair when Gemma labels every broken test as outdated (exploratory; the rule was chosen on 2026-11-07
after the repair outcomes were seen, so it needs a fresh test).

outdated_test_judge.py showed Gemma 4 31B the issue and the broken-test report of each held-back Gemma patch, without
the patch, and asked whether each broken test asserts the old behaviour the issue changes (outdated) or behaviour that
must stay (regression). Rule: if Gemma labels all broken tests outdated, keep the start patch; otherwise take the
result of the repair with the broken tests shown. Empty submissions count as failing, other ungraded runs keep the
start grade, as in lite_repair.py.

Patch sets, as in Table 4: held-out (labels: official), and Lite issues whose reference patch passes our grader
(labels: our grade of the start patch). One JSON object on stdout.

Usage: python3 outdated_tests.py > derived/outdated_tests_2026-11-07.json
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(HERE), "data", "lab-runs")
GW, MODEL = "gemma-4-31b", "google/gemma-4-31b-it"
L = lambda p: [json.loads(l) for l in open(p)]
lab = lambda p: {r["instance_id"]: r.get("resolved") for r in L(p)}

judge = {r["pid"]: r["parsed"] for r in L(os.path.join(R, "outdated-tests", "judge.jsonl"))
         if r["model"] == MODEL and r.get("parsed") is not None}


def empty(p):
    return p.get("exit_status") == "Submitted" and p.get("patch_empty", not (p.get("model_patch") or "").strip())


def one(gate, rep, start=None, ref=None):
    meta = {m["pid"]: m for m in L(os.path.join(gate, "meta.jsonl"))}
    blocked = [r["pid"] for r in L(os.path.join(gate, "runs.jsonl"))
               if r["kind"] == "patch" and r.get("decision") == "block" and meta[r["pid"]]["writer"] == GW]
    after = lab(os.path.join(rep, "tests", "labels.jsonl"))
    preds = {r["instance_id"]: r for r in L(os.path.join(rep, "tests", "preds.jsonl"))}
    out = dict(blocked=0, labeled=0, labeled_all_outdated=0, failing=0, correct=0,
               tests=dict(repaired=0, broken=0), rule=dict(repaired=0, broken=0))
    for pid in blocked:
        iid = meta[pid]["iid"]
        if iid not in preds or (ref is not None and ref.get(iid) is not True):
            continue
        y = bool(meta[pid]["y"]) if start is None else start.get(iid)
        if y is None:
            continue
        a = after.get(iid)
        a = bool(a) if a is not None else False if empty(preds[iid]) else y
        p = judge.get(pid)
        skip = bool(p and p.get("all_outdated"))
        rule = y if skip else a
        out["blocked"] += 1; out["labeled"] += p is not None; out["labeled_all_outdated"] += skip
        out["failing" if not y else "correct"] += 1
        for k, v in (("tests", a), ("rule", rule)):
            out[k]["repaired"] += (not y) and v
            out[k]["broken"] += y and not v
    return out


lite = os.path.join(R, "lite-repair")
print(json.dumps(dict(
    held_out=one(os.path.join(R, "existing-test-gate"), os.path.join(R, "test-repair")),
    lite=one(os.path.join(lite, "gate"), lite, start=lab(os.path.join(lite, "start", "labels.jsonl")),
             ref=lab(os.path.join(lite, "reference", "labels.jsonl")))), indent=1))
