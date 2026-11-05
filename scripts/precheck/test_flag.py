#!/usr/bin/env python3
"""Check B of spec/bug-token-precheck.md (addendum 2026-11-02): an existing-test flag as an upper bound.

For each of the 31B's own held-out patches, parse its grading log with SWE-bench 4.1.0's own log parser and flag the
patch if any PASS_TO_PASS test of the instance is FAILED or ERROR. PASS_TO_PASS tests are part of the SWE-bench label
and are chosen with the gold patch, so this is an upper bound, not a deployable gate. Then the paper's top-quarter
precision with Gemma's score, ties broken by the flag and then by fewer model calls.

Run from scripts/ (needs swebench 4.1.0, offline dataset cache):
  HF_DATASETS_OFFLINE=1 uv run --with swebench==4.1.0 --with scipy python precheck/test_flag.py \
      > derived/test_flag_2026-11-02.json"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import numpy as np
from datasets import load_dataset
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
from swebench.harness.test_spec.test_spec import make_test_spec

import tie_break as tb
from outside_judge_check import fresh_set

ds = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")}
RUNS = ["main-a", "main-b"]
flag, cover = {}, {}
for r in RUNS + ["regrade"]:  # regrade logs (later) replace the first grading's
    d = os.path.join(tb.RUNS, r, "eval_logs")
    for f in os.listdir(d):
        iid = f.removesuffix("-eval.txt"); inst = ds[iid]
        if r == "regrade" and iid not in flag:
            continue  # regrade folder may hold other runs' patches; only replace ours
        log = open(os.path.join(d, f), errors="replace").read()
        status = MAP_REPO_TO_PARSER[inst["repo"]](log, make_test_spec(inst))
        p2p = json.loads(inst["PASS_TO_PASS"])
        found = [t for t in p2p if t in status]
        cover[iid] = len(found) / len(p2p) if p2p else 1.0
        flag[iid] = int(any(status[t] in ("FAILED", "ERROR") for t in found))

A = tb.gemma_answers()
ho = tb.patch_set(*fresh_set(RUNS), RUNS, A)
iss, y, g, calls = ho["iss"], ho["y"], ho["X"][tb.G], ho["model_calls"]
fl = np.array([flag.get(i, 0) for i in iss]); cv = np.array([cover.get(i, 0.0) for i in iss])  # no log: unparsed
unparsed = cv < 0.9
out = dict(patches=len(y), passing=int(y.sum()), unparsed=int(unparsed.sum()),
           unparsed_ids=sorted(iss[unparsed].tolist()),
           flag_on_passing=int(fl[y == 1].sum()),  # must be 0 if the parser agrees with the grader
           flag_on_failing=int(fl[y == 0].sum()), failing=int((y == 0).sum()))
fail100 = (y == 0) & (g == 100)
out["failing_100"] = int(fail100.sum())
out["a_share_failing_100_breaking_existing_test"] = float(fl[fail100].mean())
out["a_among_parsed"] = float(fl[fail100 & ~unparsed].mean())


def ranked(*keys):  # higher is better; lexicographic
    s = np.zeros(len(y))
    for k, w in zip(keys, (1e8, 1e4, 1)):
        s = s + w * k
    return s


cands = {"gemma": ranked(g), "gemma_then_fewer_calls": ranked(g, -calls),
         "gemma_then_no_broken_test_then_fewer_calls": ranked(g, -fl, -calls)}
out["b_top_quarter"] = {}
for c, sc in cands.items():
    pt = tb.precision(sc, y, 0.25)
    bs = [tb.precision(sc[i], y[i], 0.25) for i in tb.boot(iss)]
    out["b_top_quarter"][c] = dict(point=round(pt, 3), ci=tb.ci(bs))
d = cands["gemma_then_no_broken_test_then_fewer_calls"]; e = cands["gemma_then_fewer_calls"]
dif = [tb.precision(d[i], y[i], 0.25) - tb.precision(e[i], y[i], 0.25) for i in tb.boot(iss)]
out["b_flag_minus_calls_only"] = dict(point=round(tb.precision(d, y, 0.25) - tb.precision(e, y, 0.25), 3), ci=tb.ci(dif))
out["per_patch"] = {i: dict(flag=int(f), coverage=round(float(c), 3), resolved=int(yy), gemma=float(gg))
                    for i, f, c, yy, gg in zip(iss, fl, cv, y, g)}
print(json.dumps(out, indent=1))
