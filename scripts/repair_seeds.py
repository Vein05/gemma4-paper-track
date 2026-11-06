#!/usr/bin/env python3
"""Repair across seeds (spec/repair-seeds.md). Reads data/lab-runs/repair-seeds/seed{1,2}/<arm>/{preds,labels}.jsonl and the
temperature 0 run in data/lab-runs/test-repair/. One JSON object on stdout."""
import collections, json, os, sys

from scipy.stats import binomtest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GW = "gemma-4-31b"
gate = os.path.join(ROOT, "data", "lab-runs", "existing-test-gate")
meta = {m["pid"]: m for m in map(json.loads, open(os.path.join(gate, "meta.jsonl"))) if m["writer"] == GW}
blocked = [m for pid, m in meta.items() if pid in {r["pid"] for r in map(json.loads, open(os.path.join(gate, "runs.jsonl")))
                                                  if r["kind"] == "patch" and r["writer"] == GW and r.get("decision") == "block"}]
failing = [m for m in blocked if m["y"] == 0]; passing = [m for m in blocked if m["y"] == 1]
seed_dirs = {s: os.path.join(ROOT, "data", "lab-runs", "repair-seeds", s) for s in ("seed1", "seed2")}
seed_dirs["temperature0"] = os.path.join(ROOT, "data", "lab-runs", "test-repair")


def result(d, arm):
    lab = {r["instance_id"]: r.get("resolved") for r in map(json.loads, open(os.path.join(d, arm, "labels.jsonl")))}
    return {m["iid"]: (bool(lab[m["iid"]]) if lab.get(m["iid"]) is not None else bool(m["y"])) for m in blocked}


def status(d, arm):
    return dict(collections.Counter(r["exit_status"] for r in map(json.loads, open(os.path.join(d, arm, "preds.jsonl")))))


R = {s: {a: result(d, a) for a in ("tests", "review")} for s, d in seed_dirs.items()}
out = {}
for s, r in R.items():
    t = sum(r["tests"][m["iid"]] and not r["review"][m["iid"]] for m in failing)
    v = sum(r["review"][m["iid"]] and not r["tests"][m["iid"]] for m in failing)
    out[s] = dict(tests_failing_now_passing=sum(r["tests"][m["iid"]] for m in failing), review_failing_now_passing=sum(r["review"][m["iid"]] for m in failing),
                  tests_passing_now_failing=sum(not r["tests"][m["iid"]] for m in passing), review_passing_now_failing=sum(not r["review"][m["iid"]] for m in passing),
                  stamped_tests_repaired=sum(r["tests"][m["iid"]] for m in failing if m["gemma"] == 100),
                  stamped_review_repaired=sum(r["review"][m["iid"]] for m in failing if m["gemma"] == 100),
                  stamped_tests_broken=sum(not r["tests"][m["iid"]] for m in passing if m["gemma"] == 100),
                  stamped_review_broken=sum(not r["review"][m["iid"]] for m in passing if m["gemma"] == 100),
                  tests_only=t, review_only=v, sign_test_p=round(binomtest(t, t + v, .5, alternative="greater").pvalue, 4) if t + v else 1.0,
                  exit_status=dict(tests=status(seed_dirs[s], "tests"), review=status(seed_dirs[s], "review")))
d = [sum(R[s]["tests"][m["iid"]] for s in ("seed1", "seed2")) - sum(R[s]["review"][m["iid"]] for s in ("seed1", "seed2")) for m in failing]
up, down = sum(x > 0 for x in d), sum(x < 0 for x in d)
p = binomtest(up, up + down, .5, alternative="greater").pvalue if up + down else 1.0
both_more = all(out[s]["tests_failing_now_passing"] > out[s]["review_failing_now_passing"] for s in ("seed1", "seed2"))
both_less = all(out[s]["review_failing_now_passing"] >= out[s]["tests_failing_now_passing"] for s in ("seed1", "seed2"))
out["primary"] = dict(patches_favouring_tests=up, patches_favouring_review=down, sign_test_p=round(p, 4),
                      reading="the failing tests help across runs" if both_more and p < .05 else "does not hold" if both_less else "mixed")
out["spread_of_3_runs"] = {a: dict(collections.Counter(str(sum(R[s][a][m["iid"]] for s in R)) for m in failing)) for a in ("tests", "review")}
print(json.dumps(out, indent=1))
