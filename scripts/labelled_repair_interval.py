#!/usr/bin/env python3
"""Interval for the drop in correct patches broken by the labelled repair (exploratory, 2026-11-11;
spec/hidden-test-and-failure-type-checks.md, part 3).

Builds the per-patch table of `labelled_repair_analyze.py` (run with W&B off, its output discarded) and computes, as
its `boot` does, the paired difference in correct patches broken: the repair with the broken tests shown minus the
labelled repair, summed per issue, 2,000 resamples of the 99 issues, seed 0. Also the drop in failing patches repaired.

  python3 labelled_repair_interval.py > derived/labelled_repair_interval_2026-11-11.json
"""
import collections, contextlib, io, json, os, runpy, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    argv = sys.argv
    sys.argv = [os.path.join(HERE, "labelled_repair_analyze.py"), "--no-wandb"]
    with contextlib.redirect_stdout(io.StringIO()):
        g = runpy.run_path(sys.argv[0], run_name="labelled_repair_analyze")
    sys.argv = argv
    per = g["per"]
    for x in per:
        x["broken_tests"] = int(x["y"] == 1 and x["tests"] == 0)
        x["broken_labelled"] = int(x["y"] == 1 and x["labelled"] == 0)
        x["repaired_tests"] = int(x["y"] == 0 and x["tests"] == 1)
        x["repaired_labelled"] = int(x["y"] == 0 and x["labelled"] == 1)
    out = dict(exploratory=True, spec="spec/hidden-test-and-failure-type-checks.md", patches=len(per),
               correct=sum(x["y"] for x in per),
               correct_broken=dict(tests_shown=sum(x["broken_tests"] for x in per),
                                   labelled=sum(x["broken_labelled"] for x in per)),
               fewer_correct_broken_tests_minus_labelled=g["boot"](per, "broken_tests", "broken_labelled"),
               fewer_failing_repaired_tests_minus_labelled=g["boot"](per, "repaired_tests", "repaired_labelled"),
               supplement_states=dict(fewer_correct_broken="13 [3, 25]", fewer_failing_repaired="5 [0, 10]"))
    # The same drop resampling only the issues that hold a correct held-back patch (a variant, for comparison).
    sub_iss = {x["iid"] for x in per if x["y"] == 1}
    out["variant_resampling_only_issues_with_a_correct_patch"] = g["boot"](
        [x for x in per if x["iid"] in sub_iss], "broken_tests", "broken_labelled")
    # Paired patch counts: broken with the tests shown only, with the labels only, by both.
    c = collections.Counter((x["broken_tests"], x["broken_labelled"]) for x in per if x["y"] == 1)
    out["correct_patches_paired"] = {"broken by both": c[(1, 1)], "broken with tests shown only": c[(1, 0)],
                                     "broken with labels only": c[(0, 1)], "broken by neither": c[(0, 0)]}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
