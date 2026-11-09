#!/usr/bin/env python3
"""Part 2 of spec/labelled-repair.md: passing patches among the 194 held-back patches of other writers under four
readings (no repair, the repair with the broken tests shown, the Agentless-style skip, the labelled repair), the net
difference labelled minus tests shown with a 95% interval from 2,000 issue resamples (seed 0), and stop rule 2.
No model calls. Reads data/lab-runs/labelled-repair/{jobs.jsonl,tests/,labelled/} copied back from the lab.

  python3 labelled_repair_analyze.py [--stop2] [--no-wandb] > derived/labelled_repair_2026-11-XX.json

A run that did not submit a patch, or whose patch could not be built for grading, leaves the start patch and its
official grade. An empty submission (the agent undid the whole start patch) counts as unresolved, as in lite_repair.py.
No reading is given while any patch lacks a final run or a grade (a grading timeout counts as no grade).
"""
import collections, glob, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(HERE), "data", "lab-runs")
G, LR = os.path.join(R, "existing-test-gate"), os.path.join(R, "labelled-repair")
GW = "gemma-4-31b"
L = lambda p: [json.loads(l) for l in open(p)] if os.path.exists(p) else []

jobs = L(os.path.join(LR, "jobs.jsonl"))
assert jobs and all("arm_b" in j for j in jobs), "run test_repair.py label first"
meta = {m["pid"]: m for m in L(os.path.join(G, "meta.jsonl"))}
rows = L(os.path.join(G, "runs.jsonl"))
wit = {}
for r in rows:
    if r["kind"] == "witness":
        wit.update(r["tests"])
gemma_issues = {r["instance_id"] for r in rows if r["kind"] == "patch" and r["writer"] == GW and r.get("decision") == "block"}


FINAL = ("Submitted", "LimitsExceeded", "ContextWindowExceededError")  # as in test_repair.py


def arm_results(arm):
    """pid -> (outcome, result). Outcomes: graded (result 0/1); reverted (submitted an empty diff: the agent undid the
    whole start patch, so the issue is unresolved, result 0, as in lite_repair.py); no_patch (the agent ended without
    submitting, or a server or sandbox error: the start patch stays, result None); cannot_grade (grading build error:
    the start patch stays, result None); ungraded (no grade yet, or a grading timeout: no reading until graded again)."""
    preds, tries = {}, collections.Counter()
    for r in L(os.path.join(LR, arm, "preds.jsonl")):
        preds[r["pid"]] = r  # last row per patch: a server error is redone on resume
        tries[r["pid"]] += 1
    lab = {}
    for p in glob.glob(os.path.join(LR, arm, "labels.*.jsonl")):
        writer = os.path.basename(p)[len("labels."):-len(".jsonl")]
        for r in L(p):
            lab[(r["instance_id"], writer)] = r  # last row per issue: a timeout is graded again with --retry-ungraded
    out = {}
    for pid, r in preds.items():
        iid, writer = pid.split("|")[:2]
        if r["exit_status"] not in FINAL and tries[pid] < 2:
            out[pid] = ("ungraded", None)  # a server or sandbox error not yet redone
        elif r["exit_status"] != "Submitted":
            out[pid] = ("no_patch", None)
        elif not r["model_patch"].strip():
            out[pid] = ("reverted", 0)
        else:
            g = lab.get((iid, writer))
            if g is None or g.get("status") == "timeout":
                out[pid] = ("ungraded", None)
            elif g.get("resolved") is None:
                out[pid] = ("cannot_grade", None)
            else:
                out[pid] = ("graded", int(bool(g["resolved"])))
    return out, collections.Counter(r["exit_status"] for r in preds.values())


ta, ta_status = arm_results("tests")
lb, lb_status = arm_results("labelled")
outcomes = dict(tests=dict(collections.Counter(o for o, _ in ta.values())),
                labelled=dict(collections.Counter(o for o, _ in lb.values())))


def value(res, pid, y):
    """(finished, 0/1): finished means the run ended for good and, if it submitted a patch, the patch has a grade."""
    if pid not in res:
        return False, y
    o, v = res[pid]
    return o != "ungraded", (y if v is None else v)


per = []
for j in jobs:
    pid, iid = j["pid"], j["instance_id"]
    y = int(meta[pid]["y"])
    ran_a, a = value(ta, pid, y)
    if j["arm_b"] == "keep":
        b, ran_b = y, True
    elif j["arm_b"] == "same_as_tests":
        b, ran_b = a, ran_a
    else:
        ran_b, b = value(lb, pid, y)
    skip = y if j["arm_b"] == "keep" else a  # Agentless-style: keep when all labelled outdated, else the tests arm
    per.append(dict(pid=pid, iid=iid, y=y, tests=a, labelled=b, skip=skip, ran=ran_a and ran_b, arm_b=j["arm_b"],
                    outdated_only=all(v != "PASSED" for v in wit[pid].values()), secondary=iid not in gemma_issues))


def summary(sub):
    s = dict(patches=len(sub), correct=sum(x["y"] for x in sub), failing=sum(1 - x["y"] for x in sub))
    for k in ("tests", "skip", "labelled"):
        s[k] = dict(passing=sum(x[k] for x in sub),
                    correct_broken=sum(x["y"] == 1 and x[k] == 0 for x in sub),
                    failing_repaired=sum(x["y"] == 0 and x[k] == 1 for x in sub))
    s["no_repair"] = dict(passing=s["correct"])
    return s


def boot(sub, k1, k2, n=2000):
    by = collections.defaultdict(int)
    for x in sub:
        by[x["iid"]] += x[k1] - x[k2]
    v = np.array(list(by.values()))
    rng = np.random.default_rng(0)
    d = [v[rng.integers(0, len(v), len(v))].sum() for _ in range(n)]
    return dict(diff=int(v.sum()), ci95=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))], issues=len(v))


done = [x for x in per if x["ran"]]
out = dict(patches=len(per), finished_in_both_arms=len(done), arm_b_kind=dict(collections.Counter(x["arm_b"] for x in per)),
           exit_status=dict(tests=dict(ta_status), labelled=dict(lb_status)), outcomes=outcomes)

if "--stop2" in sys.argv:  # stop rule 2 on the 40 patches drawn before any label or repair
    s = json.load(open(os.path.join(LR, "stop2_sample.json")))
    pids = set(s["outdated_only"] + s["real_regression"])
    sub = [x for x in per if x["pid"] in pids]
    fin = [x for x in sub if x["ran"]]
    sm = summary(fin)
    stop = (sm["labelled"]["correct_broken"] > sm["tests"]["correct_broken"]
            or sm["tests"]["failing_repaired"] - sm["labelled"]["failing_repaired"] >= 3)
    out["stop_rule_2"] = dict(sample=len(sub), finished=len(fin), **sm,
                              reading=("not all finished" if len(fin) < len(sub) else "stop" if stop else "go on"))
else:
    if len(done) < len(per):
        print(json.dumps(out, indent=1))
        sys.exit(f"{len(per) - len(done)} patches not finished or not graded in both arms: no reading yet")
    out["all"] = summary(per)
    out["secondary_123"] = summary([x for x in per if x["secondary"]])
    out["outdated_only"] = summary([x for x in per if x["outdated_only"]])
    out["real_regression"] = summary([x for x in per if not x["outdated_only"]])
    out["labelled_minus_tests"] = boot(per, "labelled", "tests")
    out["labelled_minus_no_repair"] = boot(per, "labelled", "y")
    out["skip_minus_tests"] = boot(per, "skip", "tests")
    out["labelled_minus_skip"] = boot(per, "labelled", "skip")
    lt = out["labelled_minus_tests"]
    out["method_claim"] = bool(lt["ci95"][0] > 0 and out["all"]["labelled"]["passing"] > out["all"]["no_repair"]["passing"])
print(json.dumps(out, indent=1))

if "--no-wandb" not in sys.argv and "--stop2" not in sys.argv:
    import wandb
    run = wandb.init(project="gemma4-paper-track", group="labelled-repair", name="labelled-repair-part2-analysis",
                     config=dict(spec="spec/labelled-repair.md", patches=len(per), bootstrap=2000, seed=0))
    run.summary.update({"method_claim": out["method_claim"], "labelled_minus_tests": out["labelled_minus_tests"]["diff"],
                        "labelled_minus_tests_ci_low": out["labelled_minus_tests"]["ci95"][0],
                        "labelled_minus_tests_ci_high": out["labelled_minus_tests"]["ci95"][1],
                        **{f"passing_{k}": out["all"][k]["passing"] for k in ("no_repair", "tests", "skip", "labelled")}})
    run.finish()
