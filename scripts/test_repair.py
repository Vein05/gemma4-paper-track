#!/usr/bin/env python3
"""Repair of the patches the existing-test gate blocks (spec/test-repair.md): Gemma 4 31B in mini-SWE-agent 1.7.0,
starting from its own blocked patch, with the failing tests shown or with a plain second look.

  prepare (lab):      python test_repair.py prepare --gate <gate run dir> --gate-jobs <jobs.jsonl> --out <dir>
  run (lab, vLLM up): python test_repair.py run --out <dir> [--workers 8] [--ids a,b] [--arms tests,review]
  analyze (this Mac): python test_repair.py analyze > derived/test_repair_2026-11-05.json
  label (this Mac):   python test_repair.py label --out <dir> --labels <labels-judge.jsonl>   (spec/labelled-repair.md)

prepare reads only gate decisions and logs (no labels). run writes <dir>/<arm>/{preds.jsonl,preds_grade.jsonl,trajs/}:
for Gemma's patches preds_grade.jsonl and trajs/<issue>.json; for other writers' patches (2026-11-07)
preds_grade.<writer>.jsonl and trajs/<pid>.json. Finished runs are tracked by patch; a run that ended on a server or
sandbox error is redone when the same command is run again.
"""
import argparse, collections, concurrent.futures as cf, gzip, json, os, re, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
GW = "gemma-4-31b"
ARMS = ("tests", "review")
STEP_LIMIT, MAX_TESTS, TAIL_LINES, TAIL_CHARS = 50, 15, 80, 4000
LOCK = threading.Lock()
HEAD = "A patch for this issue has already been applied to the repository (see `git diff`)."
REVIEW = (f"{HEAD} It may contain mistakes or break existing behaviour. Check it and fix any problem you find, keeping "
          "the issue above solved. Do not edit the test files.")


def safe(s):
    return re.sub(r"[^\w.-]", "_", s)


def tests_note(per_file):
    """per_file: [(command, [broken test names], log tail)] -> the failing-tests note of the spec."""
    parts = [f"{HEAD} Running the repository's existing tests shows that the patch breaks tests that passed before it:"]
    for cmd, names, tail in per_file:
        shown = "\n".join(f"- {n}" for n in names[:MAX_TESTS])
        more = f"\n- ... and {len(names) - MAX_TESTS} more" if len(names) > MAX_TESTS else ""
        parts.append(f"Command: `{cmd}`\nBroken tests:\n{shown}{more}\nEnd of its output:\n```\n{tail}\n```")
    parts.append("Fix the patch so these tests pass again and the issue above stays solved. Do not edit the test files.")
    return "\n\n".join(parts)


FIX_LINE = "Fix the patch so these tests pass again and the issue above stays solved. Do not edit the test files."
LABELLED_HEAD = "Judged from the issue alone, these broken tests check old behaviour that the issue asks to change:"
LABELLED_TAIL = ("For these tests, keep the behaviour the issue asks for, even if they still fail. Fix the patch so the "
                 "other broken tests pass again and the issue above stays solved. Do not edit the test files.")
MISSING = " (missing from the output: the file may not import)"
# Ways a repair run can end that belong to the agent; any other exit status (vLLM RetryError, a sandbox that did not
# build, a start patch that did not apply) is a server or sandbox error and the run is redone on resume (2026-11-07).
FINAL = ("Submitted", "LimitsExceeded", "ContextWindowExceededError")


def labelled_note(note, outdated):
    """spec/labelled-repair.md, Part 2 arm (b): the tests note with its last line replaced by the labelled list."""
    assert note.endswith(FIX_LINE)
    shown = "\n".join(f"- {n}" for n in outdated)
    return note[: -len(FIX_LINE)] + f"{LABELLED_HEAD}\n{shown}\n\n{LABELLED_TAIL}"


def broken_name(label_name, broken):
    """The patch's broken test (as the report writes it, suffix included) that the labeller named, or None when the
    name matches no broken test or more than one. The labeller sometimes drops the Django class or the suffix, and
    sometimes names a test from the log that did not break. broken: the gate's {"file::name": "failed"|"missing"}."""
    name = label_name.replace(MISSING, "").strip().lstrip("- ").strip()
    full = {t.split("::", 1)[1]: v for t, v in broken.items()}
    hits = [n for n in full if n == name] or [n for n in full if n.startswith(name + " (")]
    return hits[0] + (MISSING if full[hits[0]] == "missing" else "") if len(hits) == 1 else None


def label(a):
    """Add arm (b) to the jobs from the Part 1 labels: keep (all labelled outdated), labelled (some broken test
    labelled outdated), or same as the tests arm (none, or unparsed: arm (b)'s note would equal arm (a)'s, so arm (a)'s
    run is reused). Reads the jobs as prepared (jobs-unlabelled.jsonl once it exists), so it can be run again."""
    jp, up = os.path.join(a.out, "jobs.jsonl"), os.path.join(a.out, "jobs-unlabelled.jsonl")
    if not os.path.exists(up):
        os.rename(jp, up)
    jobs = [json.loads(l) for l in open(up)]
    broken = {r["pid"]: r.get("broken", {}) for r in map(json.loads, open(a.gate_runs)) if r["kind"] == "patch"}
    ans = {}
    for r in map(json.loads, open(a.labels)):  # first parsed answer per patch, as in labelled_repair_labels.py
        if r["model"] == a.model and (r["pid"] not in ans or ans[r["pid"]]["parsed"] is None):
            ans[r["pid"]] = r
    n, dropped = collections.Counter(), []
    with open(jp, "w") as f:
        for j in jobs:
            p = ans.get(j["pid"], {}).get("parsed") or {}
            if p.get("all_outdated") is True:
                j["arm_b"] = "keep"
            else:
                tests = p.get("tests") if isinstance(p.get("tests"), dict) else {}
                od = []
                for t, v in tests.items():
                    if v == "OUTDATED":
                        b = broken_name(t, broken[j["pid"]])
                        od += [b] if b else []
                        dropped += [] if b else [(j["pid"], t)]
                od = list(dict.fromkeys(od))
                if od:
                    j["arm_b"], j["notes"]["labelled"] = "labelled", labelled_note(j["notes"]["tests"], od)
                else:
                    j["arm_b"] = "same_as_tests"
            n[j["arm_b"]] += 1
            f.write(json.dumps(j) + "\n")
    print(dict(n))
    for pid, t in dropped:
        print("labelled outdated but not a broken test of the patch, left out:", pid, t)


def tail_of(text):
    lines = [l for l in text.splitlines() if not l.startswith("INFO:    ")]
    t = "\n".join(lines[-TAIL_LINES:])
    return t[-TAIL_CHARS:]


def prepare(a):
    sys.path.insert(0, HERE)
    from datasets import load_dataset
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    from existing_test_gate import directives
    insts = {r["instance_id"]: r for r in load_dataset(os.environ.get("SWE_DATASET", "princeton-nlp/SWE-bench_Verified"), split="test")}
    patches = {p["pid"]: p for j in map(json.loads, open(a.gate_jobs)) for p in j["patches"]}
    keep = (lambda w: w == GW) if a.writers == "gemma" else (lambda w: w not in (GW, "gold"))  # "others": 2026-11-07
    rows = [r for r in map(json.loads, open(os.path.join(a.gate, "runs.jsonl")))
            if r["kind"] == "patch" and keep(r["writer"]) and r.get("decision") == "block"]
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "jobs.jsonl"), "w") as f:
        for r in sorted(rows, key=lambda r: (r["instance_id"], r["pid"])):
            iid = r["instance_id"]; inst = insts[iid]
            cmd0 = MAP_REPO_VERSION_TO_SPECS[inst["repo"]][inst["version"]]["test_cmd"]
            tag = safe(f"{r['writer']}-{r['pid'].rsplit('|', 1)[-1]}")
            by_file = collections.defaultdict(list)
            for t in sorted(r["broken"]):
                fpath, name = t.split("::", 1)
                by_file[fpath].append(name + (" (missing from the output: the file may not import)"
                                              if r["broken"][t] == "missing" else ""))
            per_file = []
            for fpath, names in sorted(by_file.items()):
                log = os.path.join(a.gate, "logs", iid, f"patch-{tag}-1-{safe(fpath)}.txt.gz")
                tail = tail_of(gzip.open(log, "rt", errors="replace").read()) if os.path.exists(log) else "(no output kept)"
                per_file.append((" ".join([cmd0, *directives(inst["repo"], [fpath])]), names, tail))
            f.write(json.dumps(dict(instance_id=iid, pid=r["pid"], start_patch=patches[r["pid"]]["patch"],
                                    notes=dict(tests=tests_note(per_file), review=REVIEW))) + "\n")
    print(f"{len(rows)} blocked patches ({a.writers})")


def run_jobs(a):
    sys.path.insert(0, HERE)
    import yaml
    from datasets import load_dataset
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.config import builtin_config_dir
    import eval_apptainer as ev
    from existing_test_gate import ACTIVATE
    from run_gemma_mini import ApptainerSandbox, VllmModel

    class Sandbox(ApptainerSandbox):
        """The writer runs' sandbox with the repository's `testbed` environment active (spec/test-repair.md)."""

        def execute(self, command, cwd=""):
            return super().execute(ACTIVATE + command, cwd)

    insts = {r["instance_id"]: r for r in load_dataset(os.environ.get("SWE_DATASET", "princeton-nlp/SWE-bench_Verified"), split="test")}
    cfg = yaml.safe_load((builtin_config_dir / "extra" / "swebench.yaml").read_text())
    cfg["agent"]["step_limit"] = STEP_LIMIT
    if os.environ.get("REPAIR_SEED"):  # spec/repair-seeds.md: new runs need sampling; default stays temperature 0
        cfg["model"]["model_kwargs"] |= dict(temperature=float(os.environ["REPAIR_TEMPERATURE"]),
                                             seed=int(os.environ["REPAIR_SEED"]))
    jobs = [json.loads(l) for l in open(os.path.join(a.out, "jobs.jsonl"))]
    if a.ids:  # issue ids or patch ids (pid)
        ids = set(a.ids.split(","))
        jobs = [j for j in jobs if j["instance_id"] in ids or j["pid"] in ids]
    if a.pids_file:  # one pid per line (pids hold "|", so they are not passed on the command line)
        ids = {l.strip() for l in open(a.pids_file) if l.strip()}
        jobs = [j for j in jobs if j["pid"] in ids]
    todo = []
    for arm in a.arms.split(","):
        if not any(arm in j["notes"] for j in jobs):
            sys.exit(f"no job carries a note for arm {arm!r}: wrong jobs.jsonl?")
        d = os.path.join(a.out, arm); os.makedirs(os.path.join(d, "trajs"), exist_ok=True)
        p = os.path.join(d, "preds.jsonl")
        last = {}  # by patch (2026-11-07); a run that ended on a server or sandbox error is run again
        for l in (open(p) if os.path.exists(p) else []):
            r = json.loads(l); last[r["pid"]] = r["exit_status"]
        done = {pid for pid, s in last.items() if s in FINAL}
        todo += [(arm, j) for j in jobs if j["pid"] not in done and arm in j["notes"]]  # no note: arm not run
    print(f"{len(todo)} runs to do", flush=True)

    def one(arm, j):
        iid, t0 = j["instance_id"], time.time()
        model = VllmModel(model_name="hosted_vllm/" + os.environ.get("SERVED_MODEL", "gemma4-qat"),
                          model_kwargs={"api_base": os.environ.get("VLLM_BASE", "http://127.0.0.1:18000/v1"),
                                        "api_key": "none", **cfg.get("model", {}).get("model_kwargs", {})})
        env = agent = None
        try:
            env = Sandbox(**(cfg.get("environment", {}) | {"image": ev.image(iid)}))
            if not ev.apply_patch(j["start_patch"], os.path.join(env.dir, "start.diff"), "/start.diff",  # outside /testbed: not in the final diff
                                  lambda c: env.execute("cd /testbed && " + c)["returncode"]):
                raise RuntimeError("start patch does not apply")
            agent = DefaultAgent(model, env, **cfg.get("agent", {}))
            status, result = agent.run(insts[iid]["problem_statement"] + "\n\n---\n\n" + j["notes"][arm])
        except Exception as e:
            status, result = type(e).__name__, str(e)
        finally:
            if env:
                env.cleanup()
        row = dict(instance_id=iid, pid=j["pid"], arm=arm, model_patch=result if status == "Submitted" else "",
                   exit_status=status, n_calls=model.n_calls, tokens=getattr(model, "tokens", 0),
                   seconds=round(time.time() - t0))
        if status != "Submitted":
            row["error"] = str(result)[-1000:]
        d = os.path.join(a.out, arm)
        with LOCK:
            # Gemma's own patches (one per issue) keep the old names that other scripts read. Other writers: one
            # trajectory per patch and one grading file per writer, since SWE-bench grading takes one patch per issue.
            writer = j["pid"].split("|")[1] if j["pid"].count("|") >= 2 else GW
            gemma = writer == GW
            json.dump(dict(row, task_note=j["notes"][arm], messages=agent.messages if agent else []),
                      open(os.path.join(d, "trajs", f"{iid if gemma else safe(j['pid'])}.json"), "w"))
            with open(os.path.join(d, "preds.jsonl"), "a") as f:
                f.write(json.dumps(row) + "\n")
            if status == "Submitted" and result.strip():
                with open(os.path.join(d, "preds_grade.jsonl" if gemma else f"preds_grade.{safe(writer)}.jsonl"), "a") as f:
                    f.write(json.dumps(dict(instance_id=iid, model_patch=result)) + "\n")
        print(arm, iid, status, f"calls={model.n_calls}", f"{row['seconds']}s", flush=True)

    with cf.ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(lambda x: one(*x), todo))


def analyze(a):
    from scipy.stats import binomtest
    gate = os.path.join(ROOT, "data", "lab-runs", "existing-test-gate")
    out_dir = os.path.join(ROOT, "data", "lab-runs", "test-repair")
    meta = {m["pid"]: m for m in map(json.loads, open(os.path.join(gate, "meta.jsonl"))) if m["writer"] == GW}
    blocked = {r["pid"] for r in map(json.loads, open(os.path.join(gate, "runs.jsonl")))
               if r["kind"] == "patch" and r["writer"] == GW and r.get("decision") == "block"}
    after = {}
    for arm in ARMS:
        preds = {r["instance_id"]: r for r in map(json.loads, open(os.path.join(out_dir, arm, "preds.jsonl")))}
        lab = {r["instance_id"]: r for r in map(json.loads, open(os.path.join(out_dir, arm, "labels.jsonl")))}
        res = {}
        for pid, m in meta.items():
            iid = m["iid"]
            if pid in blocked and iid in lab and lab[iid].get("resolved") is not None:
                res[pid] = int(bool(lab[iid]["resolved"]))
            else:  # not blocked, no submission or not gradable: the original patch and grade
                res[pid] = m["y"]
        after[arm] = res
        after[arm + "_status"] = collections.Counter(p["exit_status"] for p in preds.values())
    stamped_fail = [p for p, m in meta.items() if m["y"] == 0 and m["gemma"] == 100]
    out = dict(gemma_patches=len(meta), blocked=len(blocked),
               blocked_failing=sum(meta[p]["y"] == 0 for p in blocked if p in meta),
               blocked_passing=sum(meta[p]["y"] == 1 for p in blocked if p in meta),
               resolved_before=sum(m["y"] for m in meta.values()))
    for arm in ARMS:
        r = after[arm]
        out[arm] = dict(
            exit_status=dict(after[arm + "_status"]),
            stamped_failing_now_passing=sum(r[p] for p in stamped_fail), of_stamped_failing=len(stamped_fail),
            blocked_failing_now_passing=sum(r[p] for p in blocked if meta[p]["y"] == 0),
            blocked_passing_now_failing=sum(1 - r[p] for p in blocked if meta[p]["y"] == 1),
            resolved_after=sum(r.values()))
    bf = [p for p in blocked if meta[p]["y"] == 0]
    t_only = sum(after["tests"][p] == 1 and after["review"][p] == 0 for p in bf)
    r_only = sum(after["tests"][p] == 0 and after["review"][p] == 1 for p in bf)
    pv = binomtest(t_only, t_only + r_only, 0.5, alternative="greater").pvalue if t_only + r_only else 1.0
    out["tests_vs_review"] = dict(tests_only=t_only, review_only=r_only, sign_test_p=round(pv, 4))
    n_t = out["tests"]["blocked_failing_now_passing"]
    out["reading"] = ("no repair" if n_t < 3 else "the failing tests help repair" if pv < 0.05
                      else "a second look is enough" if out["review"]["blocked_failing_now_passing"] >= n_t
                      else "repairs, no clear credit to the failing tests")
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("prepare"); p.add_argument("--gate", required=True); p.add_argument("--gate-jobs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--writers", choices=("gemma", "others"), default="gemma")  # others: every writer but Gemma and gold
    r = sp.add_parser("run"); r.add_argument("--out", required=True); r.add_argument("--workers", type=int, default=8)
    r.add_argument("--ids", default=""); r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--pids-file", default="")
    sp.add_parser("analyze")
    b = sp.add_parser("label"); b.add_argument("--out", required=True); b.add_argument("--labels", required=True)
    b.add_argument("--model", default="google/gemma-4-31b-it")
    b.add_argument("--gate-runs", default=os.path.join(ROOT, "data", "lab-runs", "existing-test-gate", "runs.jsonl"))
    a = ap.parse_args()
    {"prepare": prepare, "run": run_jobs, "analyze": analyze, "label": label}[a.cmd](a)


if __name__ == "__main__":
    main()
