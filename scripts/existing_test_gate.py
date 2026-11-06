#!/usr/bin/env python3
"""Existing-test gate (spec/existing-test-gate.md): pick a patch's tests from its changed code alone, run them before
and after the patch, block the patch if a test that passed twice before fails twice after.

  prepare (this Mac):  python existing_test_gate.py prepare       -> data/lab-runs/existing-test-gate/{jobs,meta}.jsonl
  run (lab, CPU only): python existing_test_gate.py run --jobs jobs.jsonl --out runs.jsonl [--workers 24] [--ids a,b]
  analyze (this Mac):  python existing_test_gate.py analyze > derived/existing_test_gate_2026-11-05.json

jobs.jsonl holds patches and no labels; labels and judge scores go to meta.jsonl, read only by analyze.
"""
import argparse, ast, collections, gzip, hashlib, json, os, re, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
OUTDIR = os.path.join(ROOT, "data", "lab-runs", "existing-test-gate")
TEST_DIRS = {"tests", "test", "testing"}
RUN_LIMIT, INSTALL_LIMIT, ISSUE_LIMIT = 1200, 1800, 7200
# the SWE-bench images keep the repo's environment in conda env `testbed`; `--contain` hides /root/.bashrc
ACTIVATE = "[ -f /opt/miniconda3/bin/activate ] && source /opt/miniconda3/bin/activate testbed >/dev/null 2>&1; "


# ---------- selection (spec, "The gate", steps 1 to 3) ----------

def is_test_path(p):
    parts = p.split("/")
    n = parts[-1]
    return (any(d in TEST_DIRS for d in parts[:-1]) or n.startswith("test_") and n.endswith(".py")
            or n.endswith("_test.py") or n in ("tests.py", "conftest.py"))


def is_test_file_name(p):
    n = p.rsplit("/", 1)[-1]
    return n.startswith("test_") and n.endswith(".py") or n.endswith("_test.py") or n == "tests.py"


def file_blocks(patch):
    """[(base path, header, body)] per file in a unified git diff."""
    out = []
    for b in re.split(r"(?m)^(?=diff --git )", patch or ""):
        m = re.match(r"diff --git a/(\S+) b/(\S+)", b)
        if m:
            head, _, body = b.partition("\n@@")
            out.append((m.group(1), head, "@@" + body if body else ""))
    return out


def changed_base_lines(body):
    """Base line numbers the hunks remove or change, and for each pure insertion the base line before it."""
    lines, old, prev_minus = set(), 0, False
    for ln in body.split("\n"):
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", ln)
        if m:
            old, prev_minus = int(m.group(1)), False
            continue
        if ln.startswith("-"):
            lines.add(old); old += 1; prev_minus = True
        elif ln.startswith("+"):
            if not prev_minus:
                lines.add(old - 1)
        elif ln.startswith("\\"):
            continue
        else:
            old += 1; prev_minus = False
    return lines


def module_name(path):
    parts = path[:-3].split("/")
    return parts[-2] if parts[-1] == "__init__" and len(parts) > 1 else parts[-1]


def dotted(path):
    p = path[:-3]
    p = p[: -len("/__init__")] if p.endswith("/__init__") else p
    for pre in ("src/", "lib/"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p.replace("/", ".")


def keep(name):
    return len(name) >= 4 and not (name.startswith("__") and name.endswith("__"))


def changed_names(src, lines, mod):
    """Names of the innermost enclosing function and class of each changed line (spec step 2)."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return {mod}
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    names = set()
    for line in lines:
        fn = cls = None
        for n in nodes:
            if n.lineno <= line <= (n.end_lineno or n.lineno):
                if isinstance(n, ast.ClassDef):
                    cls = n if cls is None or n.lineno > cls.lineno else cls
                else:
                    fn = n if fn is None or n.lineno > fn.lineno else fn
        if fn is None and cls is None:
            names.add(mod)
            continue
        for n in (fn, cls):
            if n is not None and keep(n.name):
                names.add(n.name)
    return names


def changed_code(patch, read, tracked):
    """(changed source files, changed names, module names, dotted paths). read(path) -> base text or None."""
    files, names, mods, dots = [], set(), set(), set()
    for path, head, body in file_blocks(patch):
        if (not path.endswith(".py") or is_test_path(path) or path not in tracked
                or re.search(r"(?m)^(new|deleted) file mode", head)):
            continue
        src = read(path)
        if src is None:
            continue
        mod = module_name(path)
        files.append(path); mods.add(mod); dots.add(dotted(path))
        names |= changed_names(src, changed_base_lines(body), mod)
    return files, names, mods, dots


def score_tests(names, mods, dots, tests, read):
    """{test file: score} for the candidate test files (spec step 3); zero scores left out."""
    pats = {n: re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])") for n in sorted(names)}
    out = {}
    for t in tests:
        txt = read(t)
        if txt is None:
            continue
        base = t.rsplit("/", 1)[-1]
        s = 100 if any(base in (f"test_{m}.py", f"{m}_test.py") for m in mods) else 0
        s += 10 * sum(1 for p in pats.values() if p.search(txt))
        s += 1 if any(d in txt for d in dots) else 0
        if s:
            out[t] = s
    return out


def select(patch, read, tracked):
    """Selected test files (best first) and the evidence, for one patch."""
    files, names, mods, dots = changed_code(patch, read, tracked)
    if not files:
        return dict(files=[], changed=[], names=[], scores={})
    tests = [t for t in tracked if is_test_file_name(t)]
    sc = score_tests(names, mods, dots, tests, read)
    order = sorted(sc, key=lambda t: (-sc[t], len(t), t))
    sel = [t for t in order if sc[t] >= 10][:4] or [t for t in order if sc[t] >= 1][:2]
    return dict(files=sel, changed=files, names=sorted(names), scores={t: sc[t] for t in sel})


def directives(repo, files):
    if repo != "django/django":
        return list(files)
    out = []  # SWE-bench's get_test_directives transform for Django
    for d in files:
        d = d[: -len(".py")] if d.endswith(".py") else d
        d = d[len("tests/"):] if d.startswith("tests/") else d
        out.append(d.replace("/", "."))
    return out


# ---------- decision (spec step 5) ----------

def stable_at_base(base_runs):
    """Tests PASSED in both base runs. base_runs: [statuses run 1, statuses run 2]."""
    a, b = base_runs
    return {t for t, s in a.items() if s == "PASSED" and b.get(t) == "PASSED"}


def broken(stable, statuses):
    """{test: 'failed' | 'missing'} for stable tests that fail in one patch run."""
    out = {}
    for t in stable:
        s = statuses.get(t)
        if s is None:
            out[t] = "missing"
        elif s in ("FAILED", "ERROR"):
            out[t] = "failed"
    return out


def decide(stable, run1, run2=None):
    """'block' with the tests broken in both runs, or 'pass'."""
    b1 = broken(stable, run1)
    if not b1:
        return "pass", {}
    b2 = broken(stable, run2 or {})
    both = {t: b1[t] for t in b1 if t in b2}
    return ("block", both) if both else ("pass", {})


# ---------- prepare (this Mac) ----------

def pid_of(iid, writer, patch):
    return f"{iid}|{writer}|{hashlib.md5(patch.encode()).hexdigest()[:8]}"


def prepare(a):
    sys.path.insert(0, HERE)
    from datasets import load_dataset
    from fresh_judging import load, patches
    from per_writer_leniency import G, GW, J9
    runs = ["main-a", "main-b"]
    pids, X, y, wr, iss, _ = load(J9, runs)
    P = patches(runs)
    ds = {r["instance_id"]: r for r in load_dataset(os.environ.get("SWE_DATASET", "princeton-nlp/SWE-bench_Verified"), split="test")}
    jobs, meta = collections.defaultdict(list), []
    for i, p in enumerate(pids):
        jobs[iss[i]].append(dict(pid=p, writer=str(wr[i]), patch=P[p]["patch"]))
        meta.append(dict(pid=p, iid=str(iss[i]), writer=str(wr[i]), y=int(y[i]), gemma=float(X[G][i]),
                         glm=float(X["glm-4.5"][i])))
    for iid in jobs:  # the reference patch of every issue, a passing control
        g = ds[iid]["patch"]
        jobs[iid].append(dict(pid=pid_of(iid, "gold", g), writer="gold", patch=g))
        meta.append(dict(pid=pid_of(iid, "gold", g), iid=iid, writer="gold", y=1, gemma=None, glm=None))
    first = {GW: 0, "gold": 1}  # Gemma's patch and the reference patch run first within an issue's time limit
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "jobs.jsonl"), "w") as f:
        for iid in sorted(jobs):
            ps = sorted(jobs[iid], key=lambda x: (first.get(x["writer"], 2), x["writer"], x["pid"]))
            f.write(json.dumps(dict(instance_id=iid, patches=ps)) + "\n")
    with open(os.path.join(OUTDIR, "meta.jsonl"), "w") as f:
        for m in meta:
            f.write(json.dumps(m) + "\n")
    print(dict(issues=len(jobs), patches=sum(len(v) for v in jobs.values())))


# ---------- run (lab server, CPU) ----------

def run_jobs(a):
    sys.path.insert(0, HERE)
    import concurrent.futures as cf
    import eval_apptainer as ev
    from datasets import load_dataset
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
    from swebench.harness.test_spec.test_spec import make_test_spec
    insts = {r["instance_id"]: r for r in load_dataset(os.environ.get("SWE_DATASET", "princeton-nlp/SWE-bench_Verified"), split="test")}
    jobs = [json.loads(l) for l in open(a.jobs)]
    if a.ids:
        want = set(a.ids.split(","))
        jobs = [j for j in jobs if j["instance_id"] in want]
    done = {json.loads(l)["instance_id"] for l in open(a.out)} if os.path.exists(a.out) else set()
    jobs = [j for j in jobs if j["instance_id"] not in done]
    logdir = os.path.join(os.path.dirname(os.path.abspath(a.out)), "logs")
    print(f"{len(jobs)} issues to run ({len(done)} done)", flush=True)

    def one(j):
        iid = j["instance_id"]; inst = insts[iid]; repo = inst["repo"]
        specs = MAP_REPO_VERSION_TO_SPECS[repo][inst["version"]]
        tspec = make_test_spec(inst); parse = MAP_REPO_TO_PARSER[repo]
        t_issue = time.time()
        d = os.path.join(ev.WORK, f"{iid}-etg-{uuid.uuid4().hex[:6]}"); os.makedirs(d)
        sbx = os.path.join(d, "sbx"); rows = []
        os.makedirs(os.path.join(logdir, iid), exist_ok=True)

        def keep_log(tag, text):
            with gzip.open(os.path.join(logdir, iid, f"{tag}.txt.gz"), "wt") as f:
                f.write(text)

        try:
            for attempt in range(3):
                b = ev.run([ev.APPTAINER, "build", "--sandbox", sbx, ev.image(iid)], ev.BUILD_TIMEOUT)
                if not b.returncode:
                    break
                ev.remove(sbx); time.sleep(60)
            if b.returncode:
                return [dict(instance_id=iid, kind="issue", status="build_error", detail=b.stdout[-500:])]
            for m in ev.MOUNT_DIRS:
                os.makedirs(os.path.join(sbx, m.lstrip("/")), exist_ok=True)
            ex = [ev.APPTAINER, "exec", *ev.EXEC_FLAGS, "--contain", "--cleanenv", "--writable", "--pwd", "/testbed", sbx]
            sh = lambda c, t=300: ev.run(ex + ["bash", "-c", ACTIVATE + "cd /testbed && " + c], t)
            git = "git -c safe.directory=/testbed "
            tracked = set(sh(git + "ls-files").stdout.split())
            untracked0 = set(sh(git + "ls-files --others --exclude-standard").stdout.split())
            cache = {}

            def read(p):
                if p not in cache:
                    try:
                        cache[p] = open(os.path.join(sbx, "testbed", p), errors="replace").read()
                    except OSError:
                        cache[p] = None
                return cache[p]

            def tests_run(files, tag):
                """Statuses keyed '<file>::<test>', each file in its own run (spec addendum 1); None on a time-out."""
                out = {}
                for f in files:
                    cmd = " ".join([specs["test_cmd"], *directives(repo, [f])])
                    try:
                        r = ev.run(ex + ["bash", "-c", ACTIVATE + "cd /testbed && " + cmd], RUN_LIMIT)
                    except ev.subprocess.TimeoutExpired:
                        return None
                    safe = re.sub(r"[^\w.-]", "_", f)
                    keep_log(f"{tag}-{safe}", r.stdout)
                    out.update({f"{f}::{t}": s for t, s in parse(r.stdout, tspec).items()})
                return out

            def reset():
                sh(git + "checkout -- .")
                for p in sorted(set(sh(git + "ls-files --others --exclude-standard").stdout.split()) - untracked0):
                    sh(f"rm -rf -- '{p}'")

            def apply(patch, k):
                txt = patch if patch.endswith("\n") else patch + "\n"
                open(os.path.join(sbx, f"p{k}.diff"), "w").write(txt)
                for c in ev.APPLY:
                    if sh(c.replace("/patch.diff", f"/p{k}.diff")).returncode == 0:
                        return True
                return False

            def install():
                if "install" not in specs:
                    return None
                try:
                    return sh(specs["install"], INSTALL_LIMIT).returncode
                except ev.subprocess.TimeoutExpired:
                    return "timeout"

            sel = {p["pid"]: select(p["patch"], read, tracked) for p in j["patches"]}
            base_install = install()  # same installation state as the patch runs (spec addendum 1)
            base = {}
            for f in sorted({f for s in sel.values() for f in s["files"]}):
                if time.time() - t_issue > ISSUE_LIMIT:
                    break
                base[f] = [tests_run([f], f"base-{k}") for k in (1, 2)]
            blocked = {}
            for k, p in enumerate(j["patches"]):
                pid, s = p["pid"], sel[p["pid"]]
                row = dict(instance_id=iid, kind="patch", pid=pid, writer=p["writer"], selected=s["files"],
                           scores=s["scores"], changed=s["changed"], names=s["names"][:50])
                if not s["files"]:
                    rows.append({**row, "status": "no_check", "why": "no tests selected"}); continue
                if any(base.get(f) is None or None in base[f] for f in s["files"]):
                    rows.append({**row, "status": "no_check", "why": "base run timed out or not run"}); continue
                stable = set().union(*(stable_at_base(base[f]) for f in s["files"]))
                row["stable_tests"] = len(stable)
                if not stable:
                    rows.append({**row, "status": "no_check", "why": "no test stable at base"}); continue
                if time.time() - t_issue > ISSUE_LIMIT:
                    rows.append({**row, "status": "no_check", "why": "issue time limit"}); continue
                reset()
                if not apply(p["patch"], k):
                    rows.append({**row, "status": "no_check", "why": "patch does not apply"}); continue
                row["install"] = install()
                tag = re.sub(r"[^\w.-]", "_", f"{p['writer']}-{pid.rsplit('|', 1)[-1]}")
                r1 = tests_run(s["files"], f"patch-{tag}-1")
                if r1 is None:
                    rows.append({**row, "status": "no_check", "why": "patch run timed out"}); continue
                r2 = None
                b1 = broken(stable, r1)
                if b1:  # rerun only the files holding a broken test
                    r2 = tests_run(sorted({t.split("::", 1)[0] for t in b1}), f"patch-{tag}-2")
                    if r2 is None:
                        rows.append({**row, "status": "no_check", "why": "patch rerun timed out"}); continue
                decision, bad = decide(stable, r1, r2)
                row.update(status="checked", decision=decision, broken=bad, parsed_tests=len(r1))
                rows.append(row)
                if decision == "block":
                    blocked[pid] = bad
            # witness check, after all decisions: the broken tests' files with the reference patch applied
            if blocked:
                reset()
                gold_ok = apply(insts[iid]["patch"], "gold")
                w = dict(instance_id=iid, kind="witness", gold_applied=gold_ok)
                if gold_ok:
                    w["install"] = install()
                    by_pid = {r["pid"]: r for r in rows if r.get("pid") in blocked}
                    files = sorted({f for pid in blocked for f in by_pid[pid]["selected"]})
                    st = tests_run(files, "witness-gold")
                    w["timed_out"] = st is None
                    w["tests"] = {pid: {t: (st or {}).get(t, "missing") for t in bad} for pid, bad in blocked.items()}
                rows.append(w)
            rows.append(dict(instance_id=iid, kind="issue", status="done", secs=round(time.time() - t_issue),
                             base_install=base_install, base_files=len(base),
                             base_timeouts=sum(None in v for v in base.values())))
            return rows
        except Exception as e:
            return rows + [dict(instance_id=iid, kind="issue", status="error", detail=repr(e)[-800:])]
        finally:
            ev.remove(sbx)

    os.makedirs(ev.WORK, exist_ok=True)
    with cf.ThreadPoolExecutor(a.workers) as pool, open(a.out, "a") as f:
        for fu in cf.as_completed([pool.submit(one, j) for j in jobs]):
            for r in fu.result():
                f.write(json.dumps(r) + "\n")
            f.flush()


# ---------- analyze (this Mac) ----------

def analyze(a):
    import numpy as np
    sys.path.insert(0, HERE)
    import tie_break as tb
    from outside_judge_check import fresh_set
    meta = {m["pid"]: m for m in map(json.loads, open(os.path.join(OUTDIR, "meta.jsonl")))}
    R = collections.defaultdict(list)
    for r in map(json.loads, open(os.path.join(OUTDIR, "runs.jsonl"))):
        R[r["kind"]].append(r)
    dec = {r["pid"]: r for r in R["patch"]}
    wit = {pid: t for w in R["witness"] for pid, t in (w.get("tests") or {}).items()}
    blk = lambda p: dec.get(p, {}).get("decision") == "block"
    chk = lambda p: dec.get(p, {}).get("status") == "checked"
    rows = [dict(m, block=blk(p), checked=chk(p)) for p, m in meta.items()]
    by_issue = collections.defaultdict(list)
    for r in rows:
        by_issue[r["iid"]].append(r)
    issues = sorted(by_issue)
    rng = np.random.default_rng(0)
    boots = [rng.choice(len(issues), len(issues)) for _ in range(2000)]

    def count(pred, ix=None):
        rs = [r for i in (range(len(issues)) if ix is None else ix) for r in by_issue[issues[i]] if pred(r)]
        return sum(r["block"] for r in rs), len(rs)

    def share(pred):
        k, n = count(pred)
        bs = [(lambda kn: kn[0] / kn[1] if kn[1] else np.nan)(count(pred, ix)) for ix in boots]
        return dict(blocked=k, of=n, share=round(k / n, 3) if n else None,
                    ci95=[round(float(np.nanpercentile(bs, 2.5)), 3), round(float(np.nanpercentile(bs, 97.5)), 3)])

    GW = "gemma-4-31b"
    gem = lambda r: r["writer"] == GW
    out = dict(issues=len(issues), patches=len(rows), issues_run=len({r["instance_id"] for r in R["issue"]}),
               issue_status=dict(collections.Counter(r["status"] for r in R["issue"])))
    out["primary"] = dict(
        stamped_failing=share(lambda r: gem(r) and r["y"] == 0 and r["gemma"] == 100),
        stamped_passing=share(lambda r: gem(r) and r["y"] == 1 and r["gemma"] == 100),
        all_passing_gemma=share(lambda r: gem(r) and r["y"] == 1),
        reference=share(lambda r: r["writer"] == "gold"))
    out["all_failing_gemma"] = share(lambda r: gem(r) and r["y"] == 0)
    out["others_stamped_failing"] = share(lambda r: r["writer"] not in (GW, "gold") and r["y"] == 0 and r["gemma"] == 100)
    out["others_passing"] = share(lambda r: r["writer"] not in (GW, "gold") and r["y"] == 1)
    out["coverage"] = {w: dict(checked=sum(r["checked"] for r in rows if r["writer"] == w),
                               of=sum(r["writer"] == w for r in rows)) for w in sorted({r["writer"] for r in rows})}
    out["no_check_reasons"] = dict(collections.Counter(d.get("why") for d in dec.values() if d["status"] == "no_check"))
    reasons = collections.Counter()
    for p, d in dec.items():
        if d.get("decision") == "block":
            reasons["missing only" if set(d["broken"].values()) == {"missing"} else "failed"] += 1
    out["block_reasons"] = dict(reasons)
    # a: overlap with the label-assisted 17
    tf = json.load(open(os.path.join(HERE, "derived", "test_flag_2026-11-02.json")))["per_patch"]
    st = [r for r in rows if gem(r) and r["y"] == 0 and r["gemma"] == 100]
    out["overlap_label_assisted"] = dict(
        label_flagged=sum(tf.get(r["iid"], {}).get("flag", 0) for r in st),
        gate_blocked_of_those=sum(r["block"] and tf.get(r["iid"], {}).get("flag", 0) == 1 for r in st),
        gate_blocked_outside=sum(r["block"] and tf.get(r["iid"], {}).get("flag", 0) == 0 for r in st))
    # b: witness check
    wv = collections.Counter()
    for r in rows:
        if r["block"]:
            t = wit.get(r["pid"])
            key = "no witness run" if t is None else (
                "a broken test passes with the reference" if any(s == "PASSED" for s in t.values())
                else "broken tests also fail with the reference")
            wv[(("failing" if r["y"] == 0 else "passing") + (" reference" if r["writer"] == "gold" else ""), key)] += 1
    out["witness"] = {f"{a_} | {b_}": n for (a_, b_), n in sorted(wv.items())}
    # d: gate or GLM-4.5 at 50 or less (exploratory)
    either = lambda r: r["block"] or (r["glm"] is not None and r["glm"] <= 50)
    for name, pred in (("stamped_failing", lambda r: gem(r) and r["y"] == 0 and r["gemma"] == 100),
                       ("stamped_passing", lambda r: gem(r) and r["y"] == 1 and r["gemma"] == 100)):
        rs = [r for r in rows if pred(r)]
        out.setdefault("gate_or_glm45_le50", {})[name] = dict(caught=sum(either(r) for r in rs), of=len(rs),
                                                              glm_alone=sum(r["glm"] <= 50 for r in rs))
    # e: top quarter, ranked by not blocked, then Gemma's score, then fewer model calls
    ho = tb.patch_set(*fresh_set(["main-a", "main-b"]), ["main-a", "main-b"], tb.gemma_answers())
    iss, y, g, calls = ho["iss"], ho["y"], ho["X"][tb.G], ho["model_calls"]
    gb = {r["iid"]: r["block"] for r in rows if gem(r)}
    nb = np.array([0 if gb.get(i) else 1 for i in iss])
    s_gate = nb * 1e8 + g * 1e4 - calls
    s_paper = g * 1e4 - calls
    pt = lambda s, ix=slice(None): tb.precision(s[ix], y[ix], 0.25)
    dif = [pt(s_gate, i) - pt(s_paper, i) for i in tb.boot(iss)]
    out["top_quarter"] = dict(gate_then_score_then_calls=round(pt(s_gate), 3), paper_tie_break=round(pt(s_paper), 3),
                              gain=round(pt(s_gate) - pt(s_paper), 3), gain_ci95=tb.ci(dif))
    p = out["primary"]
    k, fb, rb = p["stamped_failing"]["blocked"], p["stamped_passing"]["blocked"], p["reference"]
    ok_fb = fb <= 4 and (rb["share"] or 0) <= 0.05
    out["reading"] = ("the gate works" if k >= 11 and ok_fb else "partial" if k >= 6 and ok_fb
                      else "too many false blocks" if not ok_fb else "no fix")
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("prepare")
    r = sp.add_parser("run"); r.add_argument("--jobs", required=True); r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=24); r.add_argument("--ids", default="")
    sp.add_parser("analyze")
    a = ap.parse_args()
    {"prepare": prepare, "run": run_jobs, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
