#!/usr/bin/env python3
"""Part 1 of spec/labelled-repair.md: does Gemma's issue-only test labelling carry over to other writers' held-back
patches? Scores outdated_test_judge.py's answers (data/lab-runs/labelled-repair/labels-judge.jsonl) against the gate's
witness rows, applies stop rule 1, and gives the no-GPU counterfactual of the keep branch. No model calls.

  python3 labelled_repair_labels.py [--no-wandb] > derived/labelled_repair_labels_2026-11-07.json
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(HERE), "data", "lab-runs")
G, LR = os.path.join(R, "existing-test-gate"), os.path.join(R, "labelled-repair")
MODEL, GW = "google/gemma-4-31b-it", "gemma-4-31b"
L = lambda p: [json.loads(l) for l in open(p)]
SUFFIX = " (missing from the output: the file may not import)"


def wilson(k, n):
    if n == 0:
        return [None, None]
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


rows = L(os.path.join(G, "runs.jsonl"))
wit = {}
for r in rows:
    if r["kind"] == "witness":
        wit.update(r["tests"])
meta = {m["pid"]: m for m in L(os.path.join(G, "meta.jsonl"))}
gemma_issues = {r["instance_id"] for r in rows if r["kind"] == "patch" and r["writer"] == GW and r.get("decision") == "block"}
jobs = L(os.path.join(LR, "jobs.jsonl"))
ans = {}
for r in L(os.path.join(LR, "labels-judge.jsonl")):  # keep the first parsed answer per patch (one re-ask allowed)
    if r["model"] == MODEL and (r["pid"] not in ans or ans[r["pid"]]["parsed"] is None):
        ans[r["pid"]] = r

per, tests_agree, tests_n = [], 0, 0
for j in jobs:
    pid = j["pid"]
    w = wit[pid]
    outdated_only = all(v != "PASSED" for v in w.values())
    p = ans.get(pid, {}).get("parsed")
    flag = bool(p and p.get("all_outdated") is True)
    if p and isinstance(p.get("tests"), dict):
        truth = {t.split("::", 1)[1]: v != "PASSED" for t, v in w.items()}
        for name, lab in p["tests"].items():
            name = name.replace(SUFFIX, "").strip().lstrip("- ").strip()
            if name in truth and lab in ("OUTDATED", "REGRESSION"):
                tests_n += 1
                tests_agree += (lab == "OUTDATED") == truth[name]
    per.append(dict(pid=pid, iid=j["instance_id"], correct=bool(meta[pid]["y"]), outdated_only=outdated_only,
                    flagged=flag, parsed=p is not None, secondary=j["instance_id"] not in gemma_issues))


def rates(sub):
    od = [x for x in sub if x["outdated_only"]]
    rg = [x for x in sub if not x["outdated_only"]]
    f, w = sum(x["flagged"] for x in od), sum(x["flagged"] for x in rg)
    return dict(outdated_only=len(od), flagged=f, flag_rate=round(f / len(od), 3), flag_ci=wilson(f, len(od)),
                real_regression=len(rg), wrongly_flagged=w, wrong_flag_rate=round(w / len(rg), 3),
                wrong_flag_ci=wilson(w, len(rg)))


allr, sec = rates(per), rates([x for x in per if x["secondary"]])
fr, wr = allr["flag_rate"], allr["wrong_flag_rate"]
reading = ("part 2 as written" if fr >= 0.5 and wr <= 0.25 else
           "part 2 without the keep branch" if fr >= 0.4 and wr <= 0.35 else "stop")
cf = dict(
    correct_patches=sum(x["correct"] for x in per),
    correct_kept_from_repair=sum(x["correct"] and x["flagged"] for x in per),
    correct_outdated_only=sum(x["correct"] and x["outdated_only"] for x in per),
    correct_outdated_only_kept=sum(x["correct"] and x["outdated_only"] and x["flagged"] for x in per),
    failing_real_regression=sum((not x["correct"]) and not x["outdated_only"] for x in per),
    failing_real_regression_kept_unrepaired=sum((not x["correct"]) and (not x["outdated_only"]) and x["flagged"] for x in per),
    failing_outdated_only=sum((not x["correct"]) and x["outdated_only"] for x in per),
    failing_outdated_only_kept=sum((not x["correct"]) and x["outdated_only"] and x["flagged"] for x in per))
out = dict(patches=len(per), unparsed=sum(not x["parsed"] for x in per), all=allr, secondary_123=sec,
           per_test_agreement=dict(agree=tests_agree, matched=tests_n), stop_rule_1=reading, keep_branch=cf,
           cost_usd=round(sum(r.get("cost") or 0 for r in L(os.path.join(LR, "labels-judge.jsonl"))), 4))
print(json.dumps(out, indent=1))

if "--no-wandb" not in sys.argv:
    import wandb
    run = wandb.init(project="gemma4-paper-track", group="labelled-repair", name="labelled-repair-part1-labels",
                     config=dict(spec="spec/labelled-repair.md", model=MODEL, temperature=0, reasoning=False,
                                 prompt_fn_sha256_prefix="2b0444c9298bc4aa", patches=len(per), seed=0))
    run.summary.update({"flag_rate": fr, "wrong_flag_rate": wr, "secondary_flag_rate": sec["flag_rate"],
                        "secondary_wrong_flag_rate": sec["wrong_flag_rate"], "stop_rule_1": reading,
                        "per_test_agreement": tests_agree / tests_n if tests_n else None, **{f"keep_{k}": v for k, v in cf.items()}})
    art = wandb.Artifact("labelled-repair-part1", type="results")
    art.add_file(os.path.join(LR, "labels-judge.jsonl"))
    run.log_artifact(art)
    run.finish()
