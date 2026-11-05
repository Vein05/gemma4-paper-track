#!/usr/bin/env python3
"""Gemma's own reproduction script run before its patch, after it, and with the reference patch (spec/own-script-gate.md).

  prepare (this Mac): python3 own_script_gate.py prepare  -> data/mcsr-runs/own-script-gate/jobs.jsonl
  run (MCSR, cpuq):   python3 own_script_gate.py run --jobs jobs.jsonl --out runs.jsonl [--workers 16]
  analyze (this Mac): python3 own_script_gate.py analyze > derived/own_script_gate_2026-11-03.json

run reuses eval_apptainer.py's sandbox code (image, remove, run, EXEC_FLAGS, MOUNT_DIRS) and the agent's exec settings.
"""
import argparse, collections, json, os, re, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
OUTDIR = os.path.join(ROOT, "data", "mcsr-runs", "own-script-gate")
SCRIPT_RUN = r"\bpython3?\s+((?!-m\b|-c\b)[\w./-]+\.py)"
LIMIT = 120
EDITOR = re.compile(r"^(fix|modify|apply|patch|update|edit|change|replace|rewrite)", re.I)


def blocks(patch):
    return [b for b in re.split(r"(?m)^(?=diff --git )", patch or "") if b.strip()]


def path_of(b):
    m = re.match(r"diff --git a/(\S+) b/", b)
    return m.group(1) if m else ""


def is_new(b):
    return bool(path_of(b)) and re.search(r"(?m)^new file mode", b.split("\n@@", 1)[0]) is not None


def prepare(a):
    os.makedirs(OUTDIR, exist_ok=True)
    n = collections.Counter()
    with open(os.path.join(OUTDIR, "jobs.jsonl"), "w") as f:
        for run in ("main-a", "main-b"):
            d = os.path.join(ROOT, "data", "mcsr-runs", run, "trajs")
            for fn in sorted(os.listdir(d)):
                t = json.load(open(os.path.join(d, fn)))
                patch = t["model_patch"] or ""
                cmds = []
                for m in t["messages"]:
                    if m["role"] == "assistant":
                        b = re.findall(r"```bash\n(.*?)```", m["content"], re.S)
                        if b:
                            cmds.append(b[-1])
                # scripts that edit the source (fix_*.py, apply_*.py, ...) are not checks: use the last other script
                runs = [c for c in cmds if any(not EDITOR.search(os.path.basename(s)) for s in re.findall(SCRIPT_RUN, c))]
                added = [b for b in blocks(patch) if is_new(b)]
                job = dict(instance_id=t["instance_id"], run=run, n_calls=t["n_calls"], script=None)
                if runs:
                    last = runs[-1]
                    script = [s for s in re.findall(SCRIPT_RUN, last) if not EDITOR.search(os.path.basename(s))][-1]
                    pre = last[:last.rfind(script)]
                    cds = re.findall(r"\bcd\s+([^\s;&|]+)", pre)
                    cwd = "/testbed" if not cds else (cds[-1] if cds[-1].startswith("/") else "/testbed/" + cds[-1])
                    full = os.path.normpath(os.path.join(cwd, script))
                    if any(os.path.normpath("/testbed/" + path_of(b)) == full for b in added):
                        job.update(script=script, cwd=cwd, last_command=last[-500:],
                                   added_diff="".join(added), full_patch=patch,
                                   script_text=next(b for b in added if os.path.normpath("/testbed/" + path_of(b)) == full))
                    n["script_in_patch" if job["script"] else "script_not_in_patch"] += 1
                else:
                    n["no_script_run"] += 1
                f.write(json.dumps(job) + "\n")
    print(dict(n))


def run_jobs(a):
    sys.path.insert(0, HERE)
    import concurrent.futures as cf
    import eval_apptainer as ev
    from datasets import load_dataset
    insts = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")}
    env = {}
    try:  # mini-SWE-agent's SWE-bench environment variables, as the agent had them
        import yaml
        from minisweagent.config import builtin_config_dir
        env = yaml.safe_load((builtin_config_dir / "extra" / "swebench.yaml").read_text()).get("environment", {}).get("env", {})
    except Exception as e:
        print("no mini-SWE-agent env:", e, flush=True)
    jobs = [j for j in map(json.loads, open(a.jobs)) if j.get("script")]
    done = {json.loads(l)["instance_id"] for l in open(a.out)} if os.path.exists(a.out) else set()
    jobs = [j for j in jobs if j["instance_id"] not in done]
    print(f"{len(jobs)} issues to run ({len(done)} done)", flush=True)

    def one(j):
        iid = j["instance_id"]
        d = os.path.join(ev.WORK, f"{iid}-gate-{uuid.uuid4().hex[:6]}"); os.makedirs(d)
        sbx = os.path.join(d, "sbx"); res = []
        try:
            for attempt in range(3):
                b = ev.run([ev.APPTAINER, "build", "--sandbox", sbx, ev.image(iid)], ev.BUILD_TIMEOUT)
                if not b.returncode:
                    break
                ev.remove(sbx); time.sleep(60)
            if b.returncode:
                return [dict(instance_id=iid, cond="build", status="build_error", detail=b.stdout[-500:])]
            for m in ev.MOUNT_DIRS:
                os.makedirs(os.path.join(sbx, m.lstrip("/")), exist_ok=True)
            ex = [ev.APPTAINER, "exec", *ev.EXEC_FLAGS, "--contain", "--cleanenv", "--writable"]
            for k, v in env.items():
                ex += ["--env", f"{k}={v}"]
            sh = lambda c, t=300, cwd="/testbed": ev.run(ex + ["--pwd", cwd, sbx, "bash", "-c", c], t)
            base = set(sh("git ls-files --others --exclude-standard").stdout.split())

            def reset():
                sh("git checkout -- .")
                now = set(sh("git ls-files --others --exclude-standard").stdout.split())
                for p in sorted(now - base):
                    sh(f"rm -rf -- '{p}'")

            def apply(diffs):
                for k, txt in enumerate(diffs):
                    if not txt.endswith("\n"):
                        txt += "\n"
                    open(os.path.join(sbx, f"p{k}.diff"), "w").write(txt)
                    ok = False
                    for c in ev.APPLY:
                        if sh("cd /testbed && " + c.replace("/patch.diff", f"/p{k}.diff")).returncode == 0:
                            ok = True; break
                    if not ok:
                        return False
                return True

            gold = insts[iid]["patch"]
            for cond, diffs in (("before", [j["added_diff"]]), ("after", [j["full_patch"]]),
                                ("reference", [gold, j["added_diff"]])):
                reset()
                if not apply(diffs):
                    res.append(dict(instance_id=iid, cond=cond, status="apply_failed")); continue
                t0 = time.time()
                try:
                    r = sh(f"python {j['script']}", LIMIT, j["cwd"])
                    out, code = r.stdout, r.returncode
                except ev.subprocess.TimeoutExpired as e:
                    out = e.output.decode(errors="replace") if isinstance(e.output, bytes) else (e.output or "")
                    code = "timeout"
                out = "\n".join(l for l in out.splitlines() if not l.startswith("INFO:    "))
                ok = code == 0 and "Traceback" not in out and "AssertionError" not in out
                res.append(dict(instance_id=iid, cond=cond, status="ran", exit=code, passes=ok,
                                secs=round(time.time() - t0, 1), output=out[-3000:]))
            return res
        except Exception as e:
            return res + [dict(instance_id=iid, cond="error", status="error", detail=repr(e)[-500:])]
        finally:
            ev.remove(sbx)

    os.makedirs(ev.WORK, exist_ok=True)
    with cf.ThreadPoolExecutor(a.workers) as pool, open(a.out, "a") as f:
        for fu in cf.as_completed([pool.submit(one, j) for j in jobs]):
            for r in fu.result():
                f.write(json.dumps(r) + "\n")
            f.flush()


def analyze(a):
    import numpy as np
    sys.path.insert(0, HERE)
    from fresh_judging import load
    from per_writer_leniency import G, GW, J9
    pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
    own = np.where(wr == GW)[0]
    jobs = {j["instance_id"]: j for j in map(json.loads, open(os.path.join(OUTDIR, "jobs.jsonl")))}
    R = collections.defaultdict(dict)
    for r in map(json.loads, open(os.path.join(OUTDIR, "runs.jsonl"))):
        R[r["instance_id"]][r["cond"]] = r

    def cls(iid):
        c = R.get(iid, {})
        if not jobs[iid].get("script"):
            return "no script"
        if not all(k in c and c[k].get("status") == "ran" for k in ("before", "after")):
            return "could not run"
        b, f = c["before"]["passes"], c["after"]["passes"]
        return {(False, True): "reproduced and fixed", (True, True): "passes both", (False, False): "fails both",
                (True, False): "passes before, fails after"}[(b, f)]

    rows = []
    for i in own:
        iid = iss[i]
        rows.append(dict(iid=iid, y=int(y[i]), score=float(X[G][i]), calls=jobs[iid]["n_calls"], cls=cls(iid)))
    yv = np.array([r["y"] for r in rows]); sc = np.array([r["score"] for r in rows])
    calls = np.array([r["calls"] for r in rows]); gate = np.array([r["cls"] == "reproduced and fixed" for r in rows])
    n = len(rows); q = int(round(n / 4))

    def top(ix, use_gate):
        keys = (calls[ix], ~gate[ix], -sc[ix]) if use_gate else (calls[ix], -sc[ix])
        order = np.lexsort(keys)
        return yv[ix][order[:int(round(len(ix) / 4))]].mean()

    al = np.arange(n)
    rng = np.random.default_rng(0); B = []
    for _ in range(2000):
        ix = rng.choice(n, n)
        B.append(top(ix, True) - top(ix, False))
    out = dict(own_patches=n, top_quarter_size=q,
               top_quarter_pass_gate=round(float(top(al, True)), 3), top_quarter_pass_fewer_calls=round(float(top(al, False)), 3),
               gain=round(float(top(al, True) - top(al, False)), 3),
               gain_ci95=[round(float(np.percentile(B, 2.5)), 3), round(float(np.percentile(B, 97.5)), 3)])
    s100 = sc == 100
    out["among_100s"] = dict(n=int(s100.sum()), pass_rate=round(float(yv[s100].mean()), 3),
                             gate_kept=int((s100 & gate).sum()),
                             pass_rate_gate=round(float(yv[s100 & gate].mean()), 3) if (s100 & gate).any() else None,
                             pass_rate_rest=round(float(yv[s100 & ~gate].mean()), 3) if (s100 & ~gate).any() else None)
    tab = collections.defaultdict(lambda: collections.Counter())
    for r, s in zip(rows, s100):
        tab[r["cls"]]["pass" if r["y"] else "fail"] += 1
        if s and not r["y"]:
            tab[r["cls"]]["stamped_fail"] += 1
    out["classes"] = {k: dict(v) for k, v in tab.items()}
    ref = [R[iid]["reference"] for iid in (r["iid"] for r in rows) if R.get(iid, {}).get("reference", {}).get("status") == "ran"]
    out["script_fails_with_reference_patch"] = dict(n=len(ref), fails=sum(not r["passes"] for r in ref))
    has_check = [bool(re.search(r"(?m)^\+.*\b(assert|raise|sys\.exit)\b", jobs[r["iid"]]["script_text"]))
                 for r in rows if jobs[r["iid"]].get("script")]
    out["scripts_with_assert_raise_or_exit"] = dict(n=len(has_check), yes=int(sum(has_check)))
    g = out["gain"]; lo = out["gain_ci95"][0]
    out["reading_gate"] = "gate works" if out["top_quarter_pass_gate"] >= 0.86 and lo > 0 else "gate does not meet the rule"
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("prepare")
    r = sp.add_parser("run"); r.add_argument("--jobs", required=True); r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=16)
    sp.add_parser("analyze")
    a = ap.parse_args()
    {"prepare": prepare, "run": run_jobs, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
