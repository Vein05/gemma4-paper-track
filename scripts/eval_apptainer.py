#!/usr/bin/env python3
"""SWE-bench evaluation without Docker: run an instance's official eval script in an Apptainer sandbox built from its
SWE-bench image, then grade the log with swebench's own grading code (spec/fresh-replication.md, "Labels").

  validate: re-grade N control patches with known official labels (mini-SWE-agent bash-only entry) and report agreement.
    python3 eval_apptainer.py validate --entry 20250807_mini-v1.7.0_gpt-oss-120b --n 30 --out val.jsonl
  eval: grade predictions (JSONL with instance_id, model_patch).
    python3 eval_apptainer.py eval --preds preds.jsonl --out labels.jsonl

Environment: APPTAINER (binary), WORK (scratch dir for sandboxes and logs), HF_HOME, APPTAINER_EXEC_FLAGS and
APPTAINER_MOUNT_DIRS (as in run_gemma_mini.py).
"""
import argparse, concurrent.futures as cf, json, os, random, re, shutil, subprocess, urllib.request, uuid

from datasets import load_dataset
from swebench.harness.grading import get_eval_report
from swebench.harness.test_spec.test_spec import make_test_spec

APPTAINER = os.environ.get("APPTAINER", "apptainer")
WORK = os.environ.get("WORK", os.path.abspath("work"))
EXEC_FLAGS = os.environ.get("APPTAINER_EXEC_FLAGS", "--fakeroot --ignore-subuid").split()
MOUNT_DIRS = [d for d in os.environ.get("APPTAINER_MOUNT_DIRS", "").split(",") if d]
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com"
APPLY = ["git apply --verbose /patch.diff", "git apply --verbose --reject /patch.diff",
         "patch --batch --fuzz=5 -p1 -i /patch.diff"]  # same fallbacks as the SWE-bench harness


def image(iid):
    return f"docker://swebench/sweb.eval.x86_64.{iid.replace('__', '_1776_')}:latest"


def run(cmd, timeout):
    # one stream, interleaved, as in the SWE-bench harness log
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)


def grade(inst, patch, tag, timeout=1800):
    """Return dict(instance_id, resolved, status) for one patch."""
    iid = inst["instance_id"]
    spec = make_test_spec(inst)
    d = os.path.join(WORK, f"{iid}-{tag}-{uuid.uuid4().hex[:6]}")
    os.makedirs(d)
    sbx = os.path.join(d, "sbx")
    try:
        b = run([APPTAINER, "build", "--sandbox", sbx, image(iid)], 1200)
        if b.returncode:
            return dict(instance_id=iid, resolved=None, status="build_error", detail=b.stdout[-500:])
        for m in MOUNT_DIRS:
            os.makedirs(os.path.join(sbx, m.lstrip("/")), exist_ok=True)
        if not patch.endswith("\n"):
            patch += "\n"  # git apply rejects a last line without newline ("corrupt patch")
        open(os.path.join(sbx, "patch.diff"), "w").write(patch)  # not /tmp: --contain hides it
        open(os.path.join(sbx, "eval.sh"), "w").write(spec.eval_script)
        ex = [APPTAINER, "exec", *EXEC_FLAGS, "--contain", "--cleanenv", "--writable", sbx]
        applied, tries = None, []
        for c in APPLY:
            r = run(ex + ["bash", "-c", f"cd /testbed && {c}"], 300)
            tries.append(r.stdout[-400:])
            if r.returncode == 0:
                applied = c.split(" /")[0]
                break
        if not applied:
            return dict(instance_id=iid, resolved=False, status="patch_apply_failed", detail=tries)
        r = run(ex + ["bash", "-c", "cd /testbed && /bin/bash /eval.sh"], timeout)
        log = os.path.join(d, "test_output.txt")
        open(log, "w").write(r.stdout)
        pred = {"instance_id": iid, "model_patch": patch, "model_name_or_path": tag}
        rep = get_eval_report(test_spec=spec, prediction=pred, test_log_path=log, include_tests_status=True)
        return dict(instance_id=iid, resolved=bool(rep[iid]["resolved"]), status="graded", applied_with=applied)
    except subprocess.TimeoutExpired:
        return dict(instance_id=iid, resolved=False, status="timeout")
    finally:
        shutil.rmtree(sbx, ignore_errors=True)


def fetch(entry, iid, name):
    try:
        return urllib.request.urlopen(f"{BUCKET}/bash-only/{entry}/logs/{iid}/{name}", timeout=60).read().decode()
    except Exception:
        return None


def validate(a, insts):
    rng = random.Random(0)
    by_repo = {}
    for iid in sorted(insts):
        by_repo.setdefault(iid.rsplit("-", 1)[0], []).append(iid)
    cands = []  # round-robin over repos, alternating wanted label, until n patches with official labels
    for lst in by_repo.values():
        rng.shuffle(lst)
    want, i = True, 0
    while len(cands) < a.n and any(by_repo.values()):
        repo = sorted(by_repo)[i % len(by_repo)]; i += 1
        while by_repo[repo]:
            iid = by_repo[repo].pop()
            rep, patch = fetch(a.entry, iid, "report.json"), fetch(a.entry, iid, "patch.diff")
            if not rep or not patch or not patch.strip():
                continue
            res = json.loads(rep)[iid]["resolved"]
            if res == want:
                cands.append((iid, patch, res)); want = not want
                break
    with cf.ThreadPoolExecutor(a.workers) as pool:
        futs = {pool.submit(grade, insts[iid], patch, "val"): (iid, off) for iid, patch, off in cands}
        with open(a.out, "w") as f:
            for fu in cf.as_completed(futs):
                iid, off = futs[fu]
                r = fu.result(); r["official"] = off
                f.write(json.dumps(r) + "\n"); f.flush()
                print(iid, "official", off, "ours", r["resolved"], r["status"], flush=True)
    rows = [json.loads(l) for l in open(a.out)]
    agree = sum(r["resolved"] == r["official"] for r in rows)
    print(f"agreement {agree}/{len(rows)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("--entry", required=True); v.add_argument("--n", type=int, default=30)
    e = sub.add_parser("eval"); e.add_argument("--preds", required=True)
    for p in (v, e):
        p.add_argument("--out", required=True); p.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    insts = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")}
    if a.cmd == "validate":
        validate(a, insts)
    else:
        preds = [json.loads(l) for l in open(a.preds)]
        with cf.ThreadPoolExecutor(a.workers) as pool, open(a.out, "w") as f:
            for r in pool.map(lambda p: grade(insts[p["instance_id"]], p["model_patch"], "eval"), preds):
                f.write(json.dumps(r) + "\n"); f.flush()


if __name__ == "__main__":
    main()
