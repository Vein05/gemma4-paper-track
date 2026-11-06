#!/usr/bin/env python3
"""Gate and repair on another team's Gemma patches (spec/lite-repair-replication.md).

  prepare (Mac):      python3 lite_repair.py prepare          -> data/lite-repair/{jobs,meta}.jsonl
  grade_files (lab):  python3 lite_repair.py grade_files --gate <dir> --gate-jobs <jobs> --out <repair dir>
  analyze (Mac):      python3 lite_repair.py analyze          -> reads data/lab-runs/lite-repair/
"""
import argparse, collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
GW = "gemma-4-31b"
DATA = os.path.join(ROOT, "data", "lite-repair")
RUN = os.path.join(ROOT, "data", "lab-runs", "lite-repair")


def prepare(a):
    from datasets import load_dataset
    sys.path.insert(0, HERE)
    from existing_test_gate import pid_of
    ids = {l.strip() for l in open(os.path.join(DATA, "issues.txt")) if l.strip()}
    gold = {r["instance_id"]: r["patch"] for r in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")}
    score = {}
    for r in map(json.loads, open(os.path.join(HERE, "derived", "lite_gemma4-31b.jsonl"))):
        if r.get("parsed") is not None:
            score[r["pid"]] = r["parsed"]
    rows = [r for r in map(json.loads, open(os.path.join(ROOT, "data", "public", "third-party-lite", "patches.jsonl")))
            if r["writer"] == GW and r["iid"] in ids]
    with open(os.path.join(DATA, "jobs.jsonl"), "w") as j, open(os.path.join(DATA, "meta.jsonl"), "w") as m:
        for r in sorted(rows, key=lambda r: r["iid"]):
            g = pid_of(r["iid"], "gold", gold[r["iid"]])
            j.write(json.dumps(dict(instance_id=r["iid"], patches=[
                dict(pid=r["pid"], writer=GW, patch=r["patch"]), dict(pid=g, writer="gold", patch=gold[r["iid"]])])) + "\n")
            m.write(json.dumps(dict(pid=r["pid"], iid=r["iid"], writer=GW, y=r["y"], gemma=score.get(r["pid"]))) + "\n")
            m.write(json.dumps(dict(pid=g, iid=r["iid"], writer="gold", y=1, gemma=None)) + "\n")
    print(dict(issues=len(rows), scored=sum(r["pid"] in score for r in rows)))


def blocked_rows(path):
    return [r for r in map(json.loads, open(path)) if r["kind"] == "patch" and r["writer"] == GW and r.get("decision") == "block"]


def grade_files(a):
    from datasets import load_dataset
    gold = {r["instance_id"]: r["patch"] for r in load_dataset(os.environ["SWE_DATASET"], split="test")}
    patches = {p["pid"]: p for j in map(json.loads, open(a.gate_jobs)) for p in j["patches"]}
    rows = blocked_rows(os.path.join(a.gate, "runs.jsonl"))
    for k, get in (("start", lambda r: patches[r["pid"]]["patch"]), ("reference", lambda r: gold[r["instance_id"]])):
        with open(os.path.join(a.out, k, "preds_grade.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(dict(instance_id=r["instance_id"], model_patch=get(r))) + "\n")
    print(f"{len(rows)} blocked Gemma patches")


def analyze(a):
    from scipy.stats import binomtest
    labels = lambda p: {r["instance_id"]: r.get("resolved") for r in map(json.loads, open(p))}
    meta = {m["pid"]: m for m in map(json.loads, open(os.path.join(RUN, "gate", "meta.jsonl")))}
    runs = [json.loads(l) for l in open(os.path.join(RUN, "gate", "runs.jsonl"))]
    dec = {r["pid"]: r for r in runs if r["kind"] == "patch"}
    gem = [m for m in meta.values() if m["writer"] == GW]
    blk = [m for m in gem if dec.get(m["pid"], {}).get("decision") == "block"]
    start, ref = labels(os.path.join(RUN, "start", "labels.jsonl")), labels(os.path.join(RUN, "reference", "labels.jsonl"))
    keep = [m for m in blk if ref.get(m["iid"]) is True and start.get(m["iid"]) is not None]
    fail = [m for m in keep if start[m["iid"]] is False]
    good = [m for m in keep if start[m["iid"]] is True]
    after, status = {}, {}
    tok = {}
    for arm in ("tests", "review"):
        pr = {r["instance_id"]: r for r in map(json.loads, open(os.path.join(RUN, arm, "preds.jsonl")))}
        lab = labels(os.path.join(RUN, arm, "labels.jsonl"))
        status[arm] = dict(collections.Counter(p["exit_status"] for p in pr.values()))
        tok[arm] = dict(calls=sum(p["n_calls"] for p in pr.values()), tokens=sum(p["tokens"] for p in pr.values()))
        # no submission or not gradable: the start patch and its grade (spec/test-repair.md)
        after[arm] = {m["iid"]: bool(lab[m["iid"]]) if lab.get(m["iid"]) is not None else bool(start[m["iid"]]) for m in keep}
    t_only = sum(after["tests"][m["iid"]] and not after["review"][m["iid"]] for m in fail)
    r_only = sum(after["review"][m["iid"]] and not after["tests"][m["iid"]] for m in fail)
    pv = binomtest(t_only, t_only + r_only, 0.5, alternative="greater").pvalue if t_only + r_only else 1.0
    nt, nr = [sum(after[k][m["iid"]] for m in fail) for k in ("tests", "review")]
    stamped_f = [m for m in gem if m["y"] == 0 and m["gemma"] == 100]
    stamped_p = [m for m in gem if m["y"] == 1 and m["gemma"] == 100]
    keep_ids = {m["pid"] for m in keep}
    out = dict(
        gemma_patches=len(gem), checked=sum(dec.get(m["pid"], {}).get("status") == "checked" for m in gem),
        blocked=len(blk), blocked_analysed=len(keep), blocked_failing=len(fail), blocked_passing=len(good),
        reference_fails_our_grader=sum(ref.get(m["iid"]) is not True for m in blk),
        reference_patches_blocked=sum(dec.get(m["pid"], {}).get("decision") == "block" for m in meta.values() if m["writer"] == "gold"),
        no_check_reasons=dict(collections.Counter(d.get("why") for d in dec.values() if d["status"] == "no_check")),
        label_agreement=dict(both_fail=sum(m["y"] == 0 and start[m["iid"]] is False for m in keep),
                             both_pass=sum(m["y"] == 1 and start[m["iid"]] is True for m in keep),
                             theirs_fail_ours_pass=sum(m["y"] == 0 and start[m["iid"]] is True for m in keep),
                             theirs_pass_ours_fail=sum(m["y"] == 1 and start[m["iid"]] is False for m in keep)),
        exit_status=status, cost=tok,
        tests=dict(blocked_failing_now_passing=nt, blocked_passing_now_failing=sum(not after["tests"][m["iid"]] for m in good)),
        review=dict(blocked_failing_now_passing=nr, blocked_passing_now_failing=sum(not after["review"][m["iid"]] for m in good)),
        tests_vs_review=dict(tests_only=t_only, review_only=r_only, sign_test_p=round(pv, 4)),
        reading=("no repair" if nt < 3 else "the failing tests help repair" if nt > nr and pv < 0.05
                 else "a second look is enough" if nr >= nt else "repairs, no clear credit to the failing tests"),
        end_to_end=dict(
            stamped_failing=len(stamped_f), stamped_passing=len(stamped_p),
            stamped_failing_blocked=sum(m["pid"] in keep_ids for m in stamped_f),
            stamped_passing_blocked=sum(m["pid"] in keep_ids for m in stamped_p),
            **{f"{k}_stamped_failing_now_passing": sum(m["pid"] in keep_ids and start[m["iid"]] is False and after[k][m["iid"]] for m in stamped_f) for k in after},
            **{f"{k}_stamped_passing_now_failing": sum(m["pid"] in keep_ids and start[m["iid"]] is True and not after[k][m["iid"]] for m in stamped_p) for k in after}))
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("prepare"); sp.add_parser("analyze")
    g = sp.add_parser("grade_files"); g.add_argument("--gate", required=True); g.add_argument("--gate-jobs", required=True)
    g.add_argument("--out", required=True)
    a = ap.parse_args()
    {"prepare": prepare, "grade_files": grade_files, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
