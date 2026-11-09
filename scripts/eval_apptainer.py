#!/usr/bin/env python3
"""SWE-bench evaluation without Docker: run an instance's official eval script in an Apptainer sandbox built from its
SWE-bench image, then grade the log with swebench's own grading code (spec/fresh-replication.md, "Labels").

  validate: re-grade N control patches with known official labels (mini-SWE-agent bash-only entry) and report agreement.
    python3 eval_apptainer.py validate --entry 20250807_mini-v1.7.0_gpt-oss-120b --n 30 --out val.jsonl
  eval: grade predictions (JSONL with instance_id, model_patch).
    python3 eval_apptainer.py eval --preds preds.jsonl --out labels.jsonl
  Other datasets (spec/multilingual-replication.md): --dataset <local parquet file> --bucket-dir multilingual

Environment: APPTAINER (binary), WORK (scratch dir for sandboxes and logs), HF_HOME, APPTAINER_EXEC_FLAGS and
APPTAINER_MOUNT_DIRS (as in run_gemma_mini.py), SIF_DIR (optional: pull each image once into this folder).
"""
import argparse, concurrent.futures as cf, fcntl, json, os, random, re, shutil, subprocess, time, urllib.request, uuid

from datasets import load_dataset
from swebench.harness.grading import get_eval_report
from swebench.harness.test_spec.test_spec import make_test_spec

APPTAINER = os.environ.get("APPTAINER", "apptainer")
WORK = os.environ.get("WORK", os.path.abspath("work"))
EXEC_FLAGS = os.environ.get("APPTAINER_EXEC_FLAGS", "--fakeroot --ignore-subuid").split()
MOUNT_DIRS = [d for d in os.environ.get("APPTAINER_MOUNT_DIRS", "").split(",") if d]
SIF_DIR = os.environ.get("SIF_DIR")  # local copies of the images (local_image)
LOG_DIR = None  # set in main(): <dir of --out>/eval_logs
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com"
BUILD_TIMEOUT = int(os.environ.get("BUILD_TIMEOUT", 3600))  # matplotlib sandboxes take about 20 min on MCSR's Lustre
APPLY = ["git apply --verbose /patch.diff", "git apply --verbose --reject /patch.diff",
         "patch --batch --fuzz=5 -p1 -i /patch.diff"]  # SWE-bench's fallbacks; only judge_actor.py and own_script_gate.py still use them
CONFIG_FILES = {"tox.ini", "setup.py", "pyproject.toml"}  # SWE-bench edits these when it builds an image


def image(iid):
    return local_image(f"docker://swebench/sweb.eval.x86_64.{iid.replace('__', '_1776_').lower()}:latest")


def local_image(ref):
    """With SIF_DIR set, pull a docker:// image once into SIF_DIR and return the file, so later sandboxes need no pull.
    Docker Hub allows the lab server 100 pulls an hour (2026-10-23): a TOOMANYREQUESTS answer waits instead of failing."""
    if not SIF_DIR or not ref.startswith("docker://"):
        return ref
    os.makedirs(SIF_DIR, exist_ok=True)
    path = os.path.join(SIF_DIR, ref.rsplit("/", 1)[-1].split(":")[0] + ".sif")
    with open(path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # one pull per image across processes
        for attempt in range(40):
            if os.path.exists(path):
                return path
            tmp = f"{path[:-4]}.tmp{os.getpid()}.sif"
            r = subprocess.run([APPTAINER, "pull", "--disable-cache", tmp, ref], capture_output=True, text=True)
            if r.returncode == 0:
                os.rename(tmp, path)
                return path
            if os.path.exists(tmp):
                os.remove(tmp)
            limited = "TOOMANYREQUESTS" in r.stdout + r.stderr
            if not limited and attempt >= 2:
                break
            time.sleep(600 if limited else 60)
    raise RuntimeError(f"pull failed: {ref}: {(r.stdout + r.stderr)[-500:]}")


def remove(path):
    """Delete a sandbox. Go's module cache is read-only, so make everything writable first (2026-10-23)."""
    subprocess.run(["chmod", "-R", "u+rwX", path], capture_output=True)  # rwX: some folders lack u+x (caddy)
    shutil.rmtree(path, ignore_errors=True)


def run(cmd, timeout):
    # one stream, interleaved, as in the SWE-bench harness log
    # errors="replace": a test log with bytes that are not UTF-8 (a Go, Ruby or PHP test, 2026-11-07) crashed the whole grading job
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)


def apply_patch(patch, host_path, diff, sh):
    """Apply a patch in /testbed and return how, or None (spec/existing-test-gate.md, addendum 2). host_path is the diff
    file on this machine, diff the same file in the sandbox, sh(command) runs in /testbed and returns the exit code.
    SWE-bench's `git apply --reject` step is left out: it applied the source hunks of a patch whose config hunks fail, and
    `patch --batch` then took those hunks as already applied and reversed them, which removed the fix."""
    def is_binary(b):
        return "GIT binary patch" in b or re.search(r"(?m)^Binary files .* differ$", b)

    def is_config(b):
        m = re.match(r"diff --git a/(\S+) b/", b)
        return m and m.group(1) in CONFIG_FILES

    blocks = re.split(r"(?m)^(?=diff --git )", patch)
    no_binary = "".join(b for b in blocks if not is_binary(b))
    no_config = "".join(b for b in blocks if not is_binary(b) and not is_config(b))
    variants = list(dict.fromkeys(t for t in (patch, no_binary, no_config) if t.strip()))

    def write(text):
        with open(host_path, "w") as f:
            f.write(text if text.endswith("\n") else text + "\n")

    for text in variants:  # git apply changes nothing unless the whole text applies
        write(text)
        if sh(f"git apply --verbose {diff}") == 0:
            return "git apply --verbose" + ("" if text == patch else " (binary or config files dropped)")
    for text in variants:
        write(text)
        cmd = f"patch --batch --forward --fuzz=5 -p1 -i {diff}"
        if sh(cmd.replace("--batch", "--dry-run --batch")) == 0 and sh(cmd) == 0:
            return "patch --batch --forward --fuzz=5 -p1 -i" + ("" if text == patch else " (binary or config files dropped)")
    return None


def grade(inst, patch, tag, timeout=1800):
    """Return dict(instance_id, resolved, status) for one patch."""
    iid = inst["instance_id"]
    spec = make_test_spec(inst)
    d = os.path.join(WORK, f"{iid}-{tag}-{uuid.uuid4().hex[:6]}")
    os.makedirs(d)
    sbx = os.path.join(d, "sbx")
    step, t0, secs = "build", time.time(), {}  # step and seconds per step, so a timeout says where it happened
    try:
        for attempt in range(3):  # builds from the shared image cache fail now and then when jobs build at once
            b = run([APPTAINER, "build", "--sandbox", sbx, image(iid)], BUILD_TIMEOUT)
            if not b.returncode:
                break
            remove(sbx)
            time.sleep(60)
        secs["build"] = round(time.time() - t0)
        if b.returncode:
            return dict(instance_id=iid, resolved=None, status="build_error", detail=b.stdout[-500:], secs=secs)
        for m in MOUNT_DIRS:
            os.makedirs(os.path.join(sbx, m.lstrip("/")), exist_ok=True)
        open(os.path.join(sbx, "eval.sh"), "w").write(spec.eval_script)
        ex = [APPTAINER, "exec", *EXEC_FLAGS, "--contain", "--cleanenv", "--writable", sbx]
        tries = []

        def sh(c):
            r = run(ex + ["bash", "-c", f"cd /testbed && {c}"], 300)
            tries.append(r.stdout[-400:])
            return r.returncode

        step, t0 = "apply", time.time()
        applied = apply_patch(patch, os.path.join(sbx, "patch.diff"), "/patch.diff", sh)  # not /tmp: --contain hides it
        secs["apply"] = round(time.time() - t0)
        if not applied:
            return dict(instance_id=iid, resolved=False, status="patch_apply_failed", detail=tries, secs=secs)
        step, t0 = "tests", time.time()
        r = run(ex + ["bash", "-c", "cd /testbed && /bin/bash /eval.sh"], timeout)
        log = os.path.join(d, "test_output.txt")
        open(log, "w").write(r.stdout)
        secs["tests"] = round(time.time() - t0)
        if LOG_DIR:  # keep the test log next to the labels (WORK is deleted at the end of a job)
            os.makedirs(LOG_DIR, exist_ok=True)
            shutil.copy(log, os.path.join(LOG_DIR, f"{iid}-{tag}.txt"))
        pred = {"instance_id": iid, "model_patch": patch, "model_name_or_path": tag}
        rep = get_eval_report(test_spec=spec, prediction=pred, test_log_path=log, include_tests_status=True)
        return dict(instance_id=iid, resolved=bool(rep[iid]["resolved"]), status="graded", applied_with=applied,
                    secs=secs)
    except subprocess.TimeoutExpired as e:
        out = e.output.decode(errors="replace") if isinstance(e.output, bytes) else (e.output or "")
        return dict(instance_id=iid, resolved=False, status="timeout", step=step, secs=secs, detail=out[-2000:])
    except RuntimeError as e:  # local_image could not pull the image
        return dict(instance_id=iid, resolved=None, status="build_error", detail=str(e)[-500:], secs=secs)
    finally:
        remove(sbx)


def fetch(entry, iid, name, bucket_dir="bash-only"):
    try:
        return urllib.request.urlopen(f"{BUCKET}/{bucket_dir}/{entry}/logs/{iid}/{name}", timeout=60).read().decode()
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
            rep, patch = fetch(a.entry, iid, "report.json", a.bucket_dir), fetch(a.entry, iid, "patch.diff", a.bucket_dir)
            if not rep or not patch or not patch.strip():
                continue
            r = json.loads(rep)
            res = r.get(iid, r)["resolved"]  # most reports are keyed by issue id; GLM-4.5's are not
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
    e.add_argument("--retry-ungraded", action="store_true", help="grade timeouts and build errors again")
    for p in (v, e):
        p.add_argument("--out", required=True); p.add_argument("--workers", type=int, default=6)
        p.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified", help="Hugging Face name or local parquet")
    v.add_argument("--bucket-dir", default="bash-only", help="folder of the entry in the submissions bucket")
    a = ap.parse_args()
    global LOG_DIR
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(a.out)), "eval_logs")
    stem = os.path.basename(a.out).rsplit(".jsonl", 1)[0]
    if stem.startswith("labels."):  # one labels file per writer (test_repair.py, 2026-11-07): logs must not collide
        LOG_DIR = os.path.join(LOG_DIR, stem[len("labels."):])
    os.makedirs(WORK, exist_ok=True)
    ds = (load_dataset("parquet", data_files=a.dataset, split="train") if a.dataset.endswith(".parquet")
          else load_dataset(a.dataset, split="test"))
    insts = {r["instance_id"]: r for r in ds}
    if a.cmd == "validate":
        validate(a, insts)
    else:
        preds = [json.loads(l) for l in open(a.preds)]
        last = {}
        for l in (open(a.out) if os.path.exists(a.out) else []):
            r = json.loads(l); last[r["instance_id"]] = r.get("status")
        # --retry-ungraded (2026-11-07): a timeout or build error is graded again; readers take the last row per issue
        done = {i for i, s in last.items() if not (a.retry_ungraded and s in ("timeout", "build_error"))}
        preds = [p for p in preds if p["instance_id"] not in done]  # resume: append, skip graded issues
        print(f"{len(preds)} to grade ({len(done)} already graded)", flush=True)
        with cf.ThreadPoolExecutor(a.workers) as pool, open(a.out, "a") as f:
            futs = [pool.submit(grade, insts[p["instance_id"]], p["model_patch"], "eval") for p in preds]
            for fu in cf.as_completed(futs):  # write each label when done, so a cancelled job keeps finished ones
                f.write(json.dumps(fu.result()) + "\n"); f.flush()


if __name__ == "__main__":
    main()
