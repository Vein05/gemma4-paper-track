#!/usr/bin/env python3
"""Failure types of Gemma 4 31B's failing patches (exploratory, chosen 2026-11-07 after the results).

SWE-bench grades a patch with the issue's tests (FAIL_TO_PASS) and the other existing tests (PASS_TO_PASS). A failing
patch is a wrong fix when some issue test fails and every other listed test passes, a regression when an issue test
passes but another listed test fails, and both when both groups have a failure.

  build (needs swebench 4.1.0 and datasets; reads the grading logs):
      uv run --with swebench==4.1.0 --with datasets python -I failure_types.py build
      -> data/failure-types/test_status.jsonl, one row per patch: how many tests of each group pass
  analyze (numpy only):
      python3 failure_types.py analyze > derived/failure_types_2026-11-07.json

Patch sets: Gemma's failing held-out patches (graded in mcsr-runs/main-a and main-b, matched to the judged patch by
its id), the failing held-out patches the existing-test check held back, and the failing Lite patches it held back
(graded in lab-runs/lite-repair/start; the Lite logs are not released because they hold the other team's patches).
"""
import collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "failure-types", "test_status.jsonl")
GW = "gemma-4-31b"
L = lambda p: [json.loads(l) for l in open(p)]


def build():
    from datasets import load_dataset
    from swebench.harness.grading import get_logs_eval
    from swebench.harness.test_spec.test_spec import make_test_spec
    from fresh_judging import pid_of
    from api_quickcheck import strip_tests

    def status(inst, log):
        if not os.path.exists(log):
            return dict(log=False)
        st, ok = get_logs_eval(make_test_spec(inst), log)
        if not ok:
            return dict(log=True, parsed=False)
        ok_ = lambda t: st.get(t) in ("PASSED", "XFAIL")
        f2p, p2p = json.loads(inst["FAIL_TO_PASS"]), json.loads(inst["PASS_TO_PASS"])
        return dict(log=True, parsed=True, issue_pass=sum(map(ok_, f2p)), issue_n=len(f2p),
                    other_pass=sum(map(ok_, p2p)), other_n=len(p2p))

    rows = []
    verified = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")}
    log_of = {}
    for run in ("main-a", "main-b"):
        for r in L(os.path.join(DATA, "mcsr-runs", run, "preds.jsonl")):
            if r.get("model_patch"):
                pid = pid_of(r["instance_id"], GW, strip_tests(r["model_patch"]))
                log_of.setdefault(pid, os.path.join(DATA, "mcsr-runs", run, "eval_logs", f"{r['instance_id']}-eval.txt"))
    gate = os.path.join(DATA, "lab-runs", "existing-test-gate")
    meta = [m for m in L(os.path.join(gate, "meta.jsonl")) if m["writer"] == GW and m["y"] == 0]
    for m in meta:
        log = log_of.get(m["pid"])
        st = status(verified[m["iid"]], log) if log else dict(log=False)
        rows.append(dict(set="held-out", pid=m["pid"], iid=m["iid"], **st))

    lite = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")}
    run = os.path.join(DATA, "lab-runs", "lite-repair")
    for m in L(os.path.join(run, "gate", "meta.jsonl")):
        if m["writer"] == GW:
            st = status(lite[m["iid"]], os.path.join(run, "start", "eval_logs", f"{m['iid']}-eval.txt"))
            rows.append(dict(set="lite", pid=m["pid"], iid=m["iid"], **st))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(dict(collections.Counter((r["set"], r["log"], r.get("parsed")) for r in rows)))


def kind(r):
    if not r.get("parsed"):
        return None
    issue_ok, other_ok = r["issue_pass"] == r["issue_n"], r["other_pass"] == r["other_n"]
    return {(False, True): "wrong fix", (True, False): "regression", (False, False): "both"}.get((issue_ok, other_ok),
                                                                                                  "all listed tests pass")


def analyze():
    import numpy as np
    from fresh_judging import FAMILY, load
    rows = L(OUT)
    by = {(r["set"], r["pid"]): r for r in rows}
    out = {}

    # Gemma's failing held-out patches that all nine judges scored: types and extra trust by type.
    J9 = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
          "llama-4-maverick"]
    pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
    outside = np.mean([X[k] for k in J9 if FAMILY[k] != "gemma"], 0)
    own = [i for i, p in enumerate(pids) if wr[i] == GW and y[i] == 0]
    types = collections.defaultdict(list)
    for i in own:
        types[kind(by.get(("held-out", pids[i]), {})) or "no log"].append(i)
    out["held_out_own_failing"] = dict(n=len(own), types={
        k: dict(n=len(v), gemma_minus_outside=round(float(np.mean(X["gemma4-31b"][v] - outside[v])), 1),
                outside_mean=round(float(np.mean(outside[v])), 1)) for k, v in sorted(types.items())})

    # Failing patches the existing-test check held back: how many break one of SWE-bench's listed other tests.
    def held_back(gate_dir, failing):
        runs = L(os.path.join(gate_dir, "runs.jsonl"))
        meta = {m["pid"]: m for m in L(os.path.join(gate_dir, "meta.jsonl"))}
        return [p for p in (r["pid"] for r in runs if r["kind"] == "patch" and r.get("decision") == "block")
                if meta[p]["writer"] == GW and failing(meta[p])]

    def tally(name, pids_):
        rs = [by.get((name, p), {}) for p in pids_]
        k = collections.Counter(kind(r) or "no log" for r in rs)
        return dict(n=len(pids_), with_log=sum(bool(r.get("parsed")) for r in rs),
                    break_other_test=k["regression"] + k["both"], types=dict(k))

    gate = os.path.join(DATA, "lab-runs", "existing-test-gate")
    out["held_out_held_back_failing"] = tally("held-out", held_back(gate, lambda m: m["y"] == 0))
    # Gemma's failing held-out patches by type and the check's decision (added 2026-11-09).
    runs = {r["pid"]: r for r in L(os.path.join(gate, "runs.jsonl")) if r["kind"] == "patch"}
    cross = collections.Counter((kind(by.get(("held-out", pids[i]), {})) or "no log", runs.get(pids[i], {}).get("decision") or "no check")
                                for i in own)
    out["held_out_own_failing_by_check"] = {f"{k} | {d}": n for (k, d), n in sorted(cross.items())}
    # Lite: failing by our own grade of the start patch, among issues whose reference patch passes our grader
    # (the set lite_repair.py analyzes).
    run = os.path.join(DATA, "lab-runs", "lite-repair")
    lab = lambda p: {r["instance_id"]: r.get("resolved") for r in L(p)}
    start, ref = lab(os.path.join(run, "start", "labels.jsonl")), lab(os.path.join(run, "reference", "labels.jsonl"))
    out["lite_held_back_failing"] = tally("lite", held_back(
        os.path.join(run, "gate"), lambda m: ref.get(m["iid"]) is True and start.get(m["iid"]) is False))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"build": build, "analyze": analyze}[sys.argv[1]]()
