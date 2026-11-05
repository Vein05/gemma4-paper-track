#!/usr/bin/env python3
"""Judge as actor: a model judges a patch by running code in the patched repository (spec/judge-as-actor.md).

prepare (this Mac): the jobs. Gemma 4 31B's own held-out patches from the paper's analysis set (scored by all nine
  judges), one other-writer failing patch per issue and one other-writer passing patch per issue (seed 0), with the
  issue text, the patch as the readers saw it, the label, the writer run's model calls and the reader scores.
    python3 judge_actor.py prepare --out ../data/lab-runs/judge-as-actor/jobs.jsonl
run (lab server; vLLM serving the judge): for each job, build an Apptainer sandbox from the issue's image, apply the
  patch, run the judge in mini-SWE-agent 1.7.0 with judge_actor.yaml (step limit 15), parse its TEST and SCORE lines,
  then run its TEST command with the patch reverted and applied. Append-only runs.jsonl and trajs/; resumes.
    python3 judge_actor.py run --jobs jobs.jsonl --sets pilot --out runs/gemma --workers 6
analyze (this Mac): the spec's measures for each judge directory given.
    python3 judge_actor.py analyze --jobs ../data/lab-runs/judge-as-actor/jobs.jsonl \
        --runs gemma=../data/lab-runs/judge-as-actor/gemma qwen=../data/lab-runs/judge-as-actor/qwen \
        > derived/judge_as_actor_<date>.json

Environment for run: SERVED_MODEL (vLLM model name, default gemma4-qat), VLLM_BASE, MODEL_ID and MODEL_REVISION
(recorded), SIF_DIR, WORK, APPTAINER, APPTAINER_EXEC_FLAGS, APPTAINER_MOUNT_DIRS (as in run_gemma_mini.py).
"""
import argparse, collections, concurrent.futures as cf, json, os, re, shutil, subprocess, sys, threading, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
JUDGES = "gemma4-31b,gpt-oss-20b,qwen35-9b,glm47-flash,qwen3-coder,gpt-oss-120b,glm-4.5,kimi-k2,llama-4-maverick".split(",")
RUNS = ["main-a", "main-b"]
GEMMA, JG = "gemma-4-31b", "gemma4-31b"
TEST_LIMIT = 120  # seconds for the harness's own run of the judge's TEST command
# SWE-bench images activate the `testbed` conda env from /root/.bashrc, which `apptainer exec --contain` hides; without
# this prefix `python` is the base Miniconda 3.11 and the repository does not import (found 2026-11-03 after the Gemma
# pilot: 125 of 133 runs hit an import error). Every agent and harness command now starts with it.
ACTIVATE = "[ -f /opt/miniconda3/bin/activate ] && source /opt/miniconda3/bin/activate testbed >/dev/null 2>&1; "
LOCK = threading.Lock()


# ----------------------------------------------------------------------------------------------------------- prepare
def prepare(a):
    import numpy as np
    import fresh_judging as F
    pids, X, y, wr, iss, S = F.load(JUDGES, RUNS)
    P = F.patches(RUNS)  # pid -> iid, writer, patch (tests stripped), issue text
    calls = {}
    for r in RUNS:
        for l in open(os.path.join(F.RUNS, r, "preds.jsonl")):
            p = json.loads(l)
            calls[p["instance_id"]] = p["n_calls"]
    rng = np.random.default_rng(0)
    own = [i for i in range(len(pids)) if wr[i] == GEMMA]
    own_issues = {iss[i] for i in own}
    by_issue = collections.defaultdict(lambda: {0: [], 1: []})
    for i in range(len(pids)):
        if wr[i] != GEMMA and iss[i] in own_issues:
            by_issue[iss[i]][int(y[i])].append(i)
    rows, n = [], collections.Counter()
    for i in own:
        stamped = X[JG][i] == 100
        rows.append(dict(pid=pids[i], iid=iss[i], writer=GEMMA, y=int(y[i]), set="own", stamped=bool(stamped),
                         n_calls=calls.get(iss[i]), reader={k: float(X[k][i]) for k in JUDGES},
                         issue=P[pids[i]]["issue"], patch=P[pids[i]]["patch"]))
        n["own"] += 1; n["pilot"] += stamped
    for iid in sorted(own_issues):
        for lab, name in ((0, "others-fail"), (1, "others-pass")):
            c = by_issue[iid][lab]
            if c:
                i = c[rng.integers(len(c))]
                rows.append(dict(pid=pids[i], iid=iid, writer=str(wr[i]), y=int(y[i]), set=name, stamped=None,
                                 n_calls=None, reader={k: float(X[k][i]) for k in JUDGES},
                                 issue=P[pids[i]]["issue"], patch=P[pids[i]]["patch"]))
                n[name] += 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(dict(n), "->", a.out)


# --------------------------------------------------------------------------------------------------------------- run
SUBMIT = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


def parse_final(text):
    """TEST and SCORE lines from the submission text (or any assistant message as a fallback)."""
    score = test = None
    for m in re.finditer(r"^[\s*#>`]*SCORE\**:\s*\**\s*(\d{1,3})\b", text, re.M | re.I):
        v = int(m.group(1))
        if 0 <= v <= 100:
            score = v
    for m in re.finditer(r"^[\s*#>`]*TEST\**:\s*(.+?)\s*$", text, re.M | re.I):
        test = m.group(1).strip().strip("`*").strip()
    return score, test


def task_text(job):
    return (f"<issue>\n{job['issue'].strip()}\n</issue>\n\n<patch>\n```diff\n{job['patch'].rstrip()}\n```\n</patch>")


def model_class():
    from run_gemma_mini import VllmModel
    if os.environ.get("TOOL_MODE") == "bash":
        # spec addendum 1: gpt-oss acts through declared tools and ends its turn in the reasoning channel when asked
        # for a text code block; it gets one `bash` tool, and its call is written back as the THOUGHT plus bash
        # block that mini-SWE-agent parses (first call only, as the template allows one command per step)
        TOOLS = [{"type": "function", "function": {"name": "bash", "description": "Run one bash command in the repository sandbox and return its output.",
                  "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "the bash command"}}, "required": ["command"]}}}]

        import openai  # litellm needs the `mcp` package for requests with tools; call vLLM's endpoint directly
        client = openai.OpenAI(base_url=os.environ.get("VLLM_BASE", "http://127.0.0.1:18000/v1"), api_key="none", timeout=1800)

        class VllmModel(VllmModel):
            def query(self, messages, **kwargs):
                for attempt in range(5):
                    try:
                        response = client.chat.completions.create(
                            model=os.environ["SERVED_MODEL"], temperature=0.0, tools=TOOLS, tool_choice="auto",
                            # spec addendum 2: optional reply cap (reasoning plus answer) against runaway replies
                            **({"max_tokens": int(os.environ["MAX_TOKENS"])} if os.environ.get("MAX_TOKENS") else {}),
                            messages=[{"role": x["role"], "content": x["content"]} for x in messages])
                        break
                    except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
                        if attempt == 4:
                            raise
                        time.sleep(30)
                self.n_calls += 1
                u = getattr(response, "usage", None)
                self.tokens = getattr(self, "tokens", 0) + (getattr(u, "total_tokens", 0) or 0)
                m = response.choices[0].message
                extra = m.model_extra or {}
                text, thought = m.content or "", extra.get("reasoning_content") or extra.get("reasoning") or ""
                # after a few steps gpt-oss copies the bash blocks of its earlier turns into its reasoning; fenced
                # code is cut from the THOUGHT so the message carries exactly one block, the tool call's
                fence = re.compile(r"```[a-z]*\n.*?```", re.S)
                cmd = ""
                for tc in (m.tool_calls or [])[:1]:
                    try:
                        cmd = json.loads(tc.function.arguments).get("command", "")
                    except Exception:
                        cmd = ""
                if not cmd and "```bash" not in text:  # no call: the last bash block of its reasoning, if any
                    blocks = re.findall(r"```bash\n(.*?)```", thought, re.S)
                    cmd = blocks[-1].strip() if blocks else ""
                if cmd:
                    text = f"THOUGHT: {fence.sub('', thought).replace('```', '').strip()}\n\n```bash\n{cmd}\n```"
                return {"content": text}
    return VllmModel


def run(a):
    import yaml
    import eval_apptainer as ev
    from run_gemma_mini import ApptainerSandbox
    from minisweagent.agents.default import DefaultAgent
    VllmModel = model_class()
    cfg = yaml.safe_load(open(os.path.join(HERE, "judge_actor.yaml")))
    if a.step_limit:
        cfg["agent"]["step_limit"] = a.step_limit
    sets = set(a.sets.split(","))
    jobs = [j for j in map(json.loads, open(a.jobs))
            if ("pilot" in sets and j["set"] == "own" and j["stamped"]) or j["set"] in sets]
    if a.ids:
        want = set(a.ids.split(","))
        jobs = [j for j in jobs if j["iid"] in want]
    os.makedirs(os.path.join(a.out, "trajs"), exist_ok=True)
    runs_path = os.path.join(a.out, "runs.jsonl")
    done = {json.loads(l)["pid"] for l in open(runs_path)} if os.path.exists(runs_path) else set()
    jobs = [j for j in jobs if j["pid"] not in done]
    print(f"{len(jobs)} jobs to run ({len(done)} done)", flush=True)
    import importlib.metadata as md, socket
    with open(os.path.join(a.out, "run.json"), "a") as f:
        f.write(json.dumps(dict(started=time.strftime("%Y-%m-%dT%H:%M:%S%z"), host=socket.gethostname(), args=vars(a),
                                config=cfg, model=dict(name=os.environ.get("MODEL_ID"), served=os.environ.get("SERVED_MODEL", "gemma4-qat"),
                                                       revision=os.environ.get("MODEL_REVISION")),
                                versions={p: md.version(p) for p in ["mini-swe-agent", "litellm", "swebench"]},
                                env={k: os.environ.get(k) for k in ["APPTAINER_EXEC_FLAGS", "APPTAINER_MOUNT_DIRS", "VLLM_BASE", "SIF_DIR", "TOOL_MODE", "MAX_TOKENS"]} | {"activate": ACTIVATE})) + "\n")
    env_vars = cfg.get("environment", {}).get("env", {})

    def one(job):
        t0 = time.time()
        row = dict(pid=job["pid"], iid=job["iid"], writer=job["writer"], set=job["set"], y=job["y"])
        model = VllmModel(model_name="hosted_vllm/" + os.environ.get("SERVED_MODEL", "gemma4-qat"),
                          model_kwargs={"api_base": os.environ.get("VLLM_BASE", "http://127.0.0.1:18000/v1"),
                                        "api_key": "none", **cfg.get("model", {}).get("model_kwargs", {})})
        env = agent = None
        try:
            env = ApptainerSandbox(**(cfg.get("environment", {}) | {"image": ev.image(job["iid"])}))
            _execute = env.execute
            env.execute = lambda command, cwd="", _x=_execute: _x(ACTIVATE + command, cwd)
            sh = lambda c, t=300, cwd="/testbed": env_run(env, c, t, cwd, ev)
            # apply the patch (not committed), with the harness's fallbacks
            open(os.path.join(env.dir, "patch.diff"), "w").write(job["patch"] if job["patch"].endswith("\n") else job["patch"] + "\n")
            applied = any(sh("cd /testbed && " + c)["returncode"] == 0 for c in ev.APPLY)
            if not applied:
                row.update(status="not_applied", seconds=round(time.time() - t0)); return row
            after_patch = status_files(sh)
            row["patch_files"] = sorted(after_patch)
            agent = DefaultAgent(model, env, **cfg.get("agent", {}))
            status, result = agent.run(task_text(job))
            row.update(status=status, n_calls=model.n_calls, tokens=getattr(model, "tokens", 0))
            score, test = parse_final(result) if status == "Submitted" else (None, None)
            src = "final" if score is not None else None
            if score is None:  # fallback: the last assistant message that carries a SCORE line
                for m in reversed(agent.messages):
                    if m["role"] == "assistant":
                        s2, t2 = parse_final(m["content"])
                        if s2 is not None:
                            score, test, src = s2, test or t2, "assistant"; break
            row.update(score=score, score_source=src, test_cmd=test)
            # the judge's own files: untracked or modified after the run, not part of the patch
            now = status_files(sh)
            judge_files = sorted(now - after_patch)
            tracked_edits = sh("cd /testbed && git diff --name-only")["output"].split()
            row["judge_files"] = judge_files
            row["judge_edited_tracked"] = sorted(set(tracked_edits) - set(p for p in after_patch))
            saved = {}
            for p in judge_files:
                src_path = os.path.join(env.dir, "testbed", p)
                if os.path.isfile(src_path) and os.path.getsize(src_path) < 2_000_000:
                    saved[p] = open(src_path, "rb").read()
            row["judge_file_text"] = {p: b.decode("utf-8", "replace")[:20000] for p, b in saved.items()}
            if test:
                def put_back():
                    for p, b in saved.items():
                        d = os.path.join(env.dir, "testbed", p); os.makedirs(os.path.dirname(d), exist_ok=True)
                        open(d, "wb").write(b)
                # reverted: original code plus the judge's files
                sh("cd /testbed && git checkout -- . && git clean -fdq"); put_back()
                row["test_reverted"] = run_test(sh, test)
                # applied: patch plus the judge's files
                sh("cd /testbed && git checkout -- . && git clean -fdq")
                ok = any(sh("cd /testbed && " + c)["returncode"] == 0 for c in ev.APPLY); put_back()
                row["test_applied"] = run_test(sh, test) if ok else dict(status="apply_failed")
        except Exception as e:
            row.update(status=type(e).__name__, error=repr(e)[-1000:])
        finally:
            if env:
                env.cleanup()
        row["seconds"] = round(time.time() - t0)
        with LOCK:
            json.dump(dict(row, messages=agent.messages if agent else []),
                      open(os.path.join(a.out, "trajs", job["pid"].replace("|", "__") + ".json"), "w"))
            with open(runs_path, "a") as f:
                f.write(json.dumps(row) + "\n")
        print(job["pid"], row.get("status"), f"score={row.get('score')}", f"calls={row.get('n_calls')}", f"{row['seconds']}s", flush=True)
        return row

    os.makedirs(ev.WORK, exist_ok=True)
    with cf.ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(one, jobs))


FINAL_ASK = ("You have used all your commands. You cannot run any more commands. Decide now from what you have already "
             "seen. Reply with only the final command, with your own test command and score filled in:\n\n```bash\n"
             "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && echo \"TEST: python judge_test.py\" && echo \"SCORE: 85\"\n```")


def parse_submit(text):
    """SCORE and TEST from a reply that holds the submission command (its echo strings), else from its lines."""
    score, test = parse_final(text)
    if score is None and SUBMIT in text:
        m = re.search(r"```bash\n(.*?)```", text, re.S)
        parts = re.findall(r"""echo\s+(?:"([^"]*)"|'([^']*)'|(\S+))""", m.group(1) if m else text)
        score, test = parse_final("\n".join(x or y or z for x, y, z in parts))
    return score, test


def finalize(a):
    """Spec addendum 3: one more call for runs that hit the step limit, asking for the final command now; then the
    harness runs the judge's TEST with the patch reverted and applied in a fresh sandbox, as in run."""
    import eval_apptainer as ev
    from run_gemma_mini import ApptainerSandbox
    import yaml
    VllmModel = model_class()
    cfg = yaml.safe_load(open(os.path.join(HERE, "judge_actor.yaml")))
    jobs = {j["pid"]: j for j in map(json.loads, open(a.jobs))}
    src = [r for r in map(json.loads, open(os.path.join(a.src, "runs.jsonl"))) if r["status"] == "LimitsExceeded"]
    os.makedirs(os.path.join(a.out, "trajs"), exist_ok=True)
    runs_path = os.path.join(a.out, "runs.jsonl")
    done = {json.loads(l)["pid"] for l in open(runs_path)} if os.path.exists(runs_path) else set()
    src = [r for r in src if r["pid"] not in done]
    print(f"{len(src)} runs to finalize ({len(done)} done)", flush=True)
    with open(os.path.join(a.out, "run.json"), "a") as f:
        f.write(json.dumps(dict(started=time.strftime("%Y-%m-%dT%H:%M:%S%z"), args=vars(a), ask=FINAL_ASK,
                                model=dict(name=os.environ.get("MODEL_ID"), served=os.environ.get("SERVED_MODEL"),
                                           revision=os.environ.get("MODEL_REVISION")),
                                env={k: os.environ.get(k) for k in ["TOOL_MODE", "MAX_TOKENS", "VLLM_BASE"]})) + "\n")

    def one(r):
        t0 = time.time()
        job, name = jobs[r["pid"]], r["pid"].replace("|", "__") + ".json"
        msgs = json.load(open(os.path.join(a.src, "trajs", name)))["messages"]
        while msgs and msgs[-1]["role"] == "user" and not msgs[-1]["content"].strip():
            msgs = msgs[:-1]
        msgs = msgs + [{"role": "user", "content": FINAL_ASK}]
        row = dict(pid=r["pid"], iid=r["iid"], writer=r["writer"], set=r["set"], y=r["y"], patch_files=r.get("patch_files"),
                   judge_files=r.get("judge_files"), judge_edited_tracked=r.get("judge_edited_tracked"))
        model = VllmModel(model_name="hosted_vllm/" + os.environ.get("SERVED_MODEL", "gemma4-qat"),
                          model_kwargs={"api_base": os.environ.get("VLLM_BASE", "http://127.0.0.1:18000/v1"),
                                        "api_key": "none", **cfg.get("model", {}).get("model_kwargs", {})})
        env = None
        try:
            reply = model.query(msgs)["content"]
            score, test = parse_submit(reply)
            row.update(status="Finalized" if score is not None else "NoScore", submitted=SUBMIT in reply,
                       n_calls=(r.get("n_calls") or 0) + model.n_calls, tokens=(r.get("tokens") or 0) + getattr(model, "tokens", 0),
                       score=score, score_source="forced_final" if score is not None else None, test_cmd=test, reply=reply[-5000:])
            msgs.append({"role": "assistant", "content": reply})
            saved = {p: t.encode() for p, t in (r.get("judge_file_text") or {}).items()}
            row["judge_file_text"] = r.get("judge_file_text")
            if test:
                env = ApptainerSandbox(**(cfg.get("environment", {}) | {"image": ev.image(job["iid"])}))
                sh = lambda c, t=300, cwd="/testbed": env_run(env, c, t, cwd, ev)

                def put_back():
                    for p, b in saved.items():
                        d = os.path.join(env.dir, "testbed", p); os.makedirs(os.path.dirname(d), exist_ok=True)
                        open(d, "wb").write(b)
                put_back()  # reverted: original code plus the judge's files
                row["test_reverted"] = run_test(sh, test)
                sh("cd /testbed && git checkout -- . && git clean -fdq")
                open(os.path.join(env.dir, "patch.diff"), "w").write(job["patch"] if job["patch"].endswith("\n") else job["patch"] + "\n")
                ok = any(sh("cd /testbed && " + c)["returncode"] == 0 for c in ev.APPLY); put_back()
                row["test_applied"] = run_test(sh, test) if ok else dict(status="apply_failed")
        except Exception as e:
            row.update(status=type(e).__name__, error=repr(e)[-1000:])
        finally:
            if env:
                env.cleanup()
        row["seconds"] = round(time.time() - t0)
        with LOCK:
            json.dump(dict(row, messages=msgs), open(os.path.join(a.out, "trajs", name), "w"))
            with open(runs_path, "a") as f:
                f.write(json.dumps(row) + "\n")
        print(r["pid"], row.get("status"), f"score={row.get('score')}", f"{row['seconds']}s", flush=True)

    os.makedirs(ev.WORK, exist_ok=True)
    with cf.ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(one, src))


def env_run(env, command, timeout, cwd, ev):
    """Run a command in the sandbox with the harness's own timeout (the agent's env.execute has the agent's)."""
    cmd = [ev.APPTAINER, "exec", *ev.EXEC_FLAGS, "--contain", "--cleanenv", "--writable", "--pwd", cwd]
    for k, v in env.config.env.items():
        cmd += ["--env", f"{k}={v}"]
    cmd += [env.dir, "bash", "-c", ACTIVATE + command]
    try:
        r = subprocess.run(cmd, text=True, timeout=timeout, encoding="utf-8", errors="replace",
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, code = r.stdout, r.returncode
    except subprocess.TimeoutExpired as e:
        out = e.output.decode(errors="replace") if isinstance(e.output, bytes) else (e.output or "")
        code = "timeout"
    out = "\n".join(l for l in out.splitlines() if not l.startswith("INFO:    "))
    return {"output": out, "returncode": code}


def status_files(sh):
    """Paths changed or untracked in /testbed (git status, porcelain)."""
    out = sh("cd /testbed && git status --porcelain --untracked-files=all")["output"]
    return {l[3:].strip().split(" -> ")[-1] for l in out.splitlines() if len(l) > 3}


def run_test(sh, test):
    t0 = time.time()
    r = sh(f"cd /testbed && {test}", TEST_LIMIT)
    out, code = r["output"], r["returncode"]
    passes = code == 0 and "Traceback" not in out and "AssertionError" not in out
    return dict(status="ran", exit=code, passes=passes, secs=round(time.time() - t0, 1), output=out[-3000:])


# ----------------------------------------------------------------------------------------------------------- analyze
def analyze(a):
    import numpy as np
    from self_judging_replication import auroc
    jobs = {j["pid"]: j for j in map(json.loads, open(a.jobs))}
    judges = dict(kv.split("=", 1) for kv in a.runs)
    rng = np.random.default_rng(0)
    B = a.boot

    def ci(vals):
        v = np.array([x for x in vals if x is not None and not np.isnan(x)], float)
        return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] if len(v) else None

    def boot_issues(rows, fn):
        """fn(list of rows) -> number; resample issues with replacement."""
        by = collections.defaultdict(list)
        for r in rows:
            by[r["iid"]].append(r)
        keys = sorted(by)
        est = fn(rows)
        draws = []
        for _ in range(B):
            pick = rng.choice(len(keys), len(keys), replace=True)
            draws.append(fn([r for k in pick for r in by[keys[k]]]))
        return dict(value=round(float(est), 3) if est is not None else None, ci=ci(draws))

    out = {}
    for name, d in judges.items():
        R = [json.loads(l) for l in open(os.path.join(d, "runs.jsonl"))]
        for r in R:
            j = jobs[r["pid"]]
            r.update(reader=j["reader"], n_calls=j["n_calls"], stamped=j["stamped"])
            r["flag"] = bool(r.get("test_reverted", {}).get("passes") is False and r.get("test_applied", {}).get("passes") is True)
        readable = [r for r in R if r.get("score") is not None]
        own = [r for r in readable if r["set"] == "own"]
        of = [r for r in readable if r["set"] == "others-fail"]
        res = dict(n_runs=len(R), n_readable=len(readable),
                   status=collections.Counter(r.get("status") for r in R),
                   score_source=collections.Counter(r.get("score_source") for r in R),
                   n_own=len(own), n_others_fail=len(of), n_others_pass=sum(r["set"] == "others-pass" for r in readable))

        def approval(rows, cut=100):
            return sum(r["score"] >= cut for r in rows) / len(rows) if rows else None
        groups = {"own_fail": [r for r in own if r["y"] == 0], "own_pass": [r for r in own if r["y"] == 1],
                  "others_fail": of, "others_pass": [r for r in readable if r["set"] == "others-pass"]}
        res["approval_100"] = {g: boot_issues(v, approval) for g, v in groups.items() if v}
        res["approval_90"] = {g: boot_issues(v, lambda rows: approval(rows, 90)) for g, v in groups.items() if v}
        res["reader_approval_100"] = {g: round(sum(r["reader"][JG] >= 100 for r in v) / len(v), 3) for g, v in groups.items() if v}

        # leniency with the paper's reader panel (judges outside Gemma's family) as the reference
        panel = [k for k in JUDGES if k != JG]
        def excess(r, score_key):
            s = r["score"] if score_key == "actor" else r["reader"][JG]
            return s - float(np.mean([r["reader"][k] for k in panel]))
        def leniency(rows, key="actor"):
            a_ = [excess(r, key) for r in rows if r["set"] == "own" and r["y"] == 0]
            b_ = [excess(r, key) for r in rows if r["set"] == "others-fail"]
            return float(np.mean(a_) - np.mean(b_)) if a_ and b_ else None
        fail_rows = [r for r in readable if (r["set"] == "own" and r["y"] == 0) or r["set"] == "others-fail"]
        if name.startswith("gemma") and of:
            res["leniency_actor_vs_reader_panel"] = boot_issues(fail_rows, leniency)
            res["leniency_reader_same_patches"] = boot_issues(fail_rows, lambda rows: leniency(rows, "reader"))

        # ranking among own patches
        def top_quarter(rows, key):
            rows = sorted(rows, key=key)
            k = max(1, round(len(rows) / 4))
            return sum(r["y"] for r in rows[:k]) / k
        actor_key = lambda r: (-r["score"], -int(r["flag"]), r["n_calls"] if r["n_calls"] is not None else 1e9)
        reader_key = lambda r: (-r["reader"][JG], r["n_calls"] if r["n_calls"] is not None else 1e9)
        if own:
            res["top_quarter_actor"] = boot_issues(own, lambda rows: top_quarter(rows, actor_key))
            res["top_quarter_reader_fewer_calls"] = boot_issues(own, lambda rows: top_quarter(rows, reader_key))
            res["top_quarter_gain"] = boot_issues(own, lambda rows: top_quarter(rows, actor_key) - top_quarter(rows, reader_key))
            res["auroc_actor_own"] = boot_issues(own, lambda rows: auroc(np.array([r["score"] for r in rows], float), np.array([r["y"] for r in rows])))
            res["auroc_reader_own_same_patches"] = boot_issues(own, lambda rows: auroc(np.array([r["reader"][JG] for r in rows], float), np.array([r["y"] for r in rows])))
            res["auroc_gain_actor_minus_reader"] = boot_issues(own, lambda rows: auroc(np.array([r["score"] for r in rows], float), np.array([r["y"] for r in rows]))
                                                          - auroc(np.array([r["reader"][JG] for r in rows], float), np.array([r["y"] for r in rows])))
            st = [r for r in own if r["stamped"]]
            if st:
                res["n_stamped"] = len(st)
                res["auroc_actor_within_stamped"] = boot_issues(st, lambda rows: auroc(np.array([r["score"] for r in rows], float), np.array([r["y"] for r in rows])))
                res["approval_100_stamped"] = {g: boot_issues(v, approval) for g, v in
                                                {"fail": [r for r in st if r["y"] == 0], "pass": [r for r in st if r["y"] == 1]}.items() if v}
            # Qwen3-32B reader scores on the same patches, if present (qwen3-32b-local)
            qr = os.path.join(HERE, "derived", "fresh_qwen3-32b-local.jsonl")
            if name.startswith("qwen") and os.path.exists(qr):
                q = {}
                for l in open(qr):
                    x = json.loads(l)
                    if x.get("parsed") is not None:
                        q[x["pid"]] = float(x["parsed"])
                ow = [r for r in own if r["pid"] in q]
                res["n_with_qwen_reader"] = len(ow)
                res["auroc_qwen_reader_same_patches"] = boot_issues(ow, lambda rows: auroc(np.array([q[r["pid"]] for r in rows], float), np.array([r["y"] for r in rows])))
                res["auroc_qwen_actor_minus_qwen_reader"] = boot_issues(ow, lambda rows: auroc(np.array([r["score"] for r in rows], float), np.array([r["y"] for r in rows]))
                                                                         - auroc(np.array([q[r["pid"]] for r in rows], float), np.array([r["y"] for r in rows])))

        # the actor's test
        with_test = [r for r in R if r.get("test_cmd")]
        res["test"] = dict(
            n_with_test_cmd=len(with_test),
            flag_share_all=round(sum(r["flag"] for r in R) / len(R), 3) if R else None,
            flag_share_own_pass=round(np.mean([r["flag"] for r in own if r["y"] == 1]), 3) if own else None,
            flag_share_own_fail=round(np.mean([r["flag"] for r in own if r["y"] == 0]), 3) if own else None,
            own_pass_rate_flagged=round(np.mean([r["y"] for r in own if r["flag"]]), 3) if any(r["flag"] for r in own) else None,
            own_pass_rate_unflagged=round(np.mean([r["y"] for r in own if not r["flag"]]), 3) if any(not r["flag"] for r in own) else None,
            stamped_fail_caught_by_flag=sum(1 for r in own if r["stamped"] and r["y"] == 0 and not r["flag"]),
            assert_share=round(np.mean([has_assert(r) for r in with_test]), 3) if with_test else None,
            reverted_pass_applied_pass=sum(1 for r in R if r.get("test_reverted", {}).get("passes") and r.get("test_applied", {}).get("passes")),
            reverted_fail_applied_fail=sum(1 for r in R if r.get("test_reverted", {}).get("passes") is False and r.get("test_applied", {}).get("passes") is False),
            judge_edited_tracked=sum(1 for r in R if r.get("judge_edited_tracked")))
        res["cost"] = dict(calls_mean=round(float(np.mean([r["n_calls"] for r in R if r.get("n_calls")])), 2) if R else None,
                           seconds_median=float(np.median([r["seconds"] for r in R])) if R else None)
        out[name] = res
    json.dump(out, sys.stdout, indent=1, default=lambda o: dict(o) if isinstance(o, collections.Counter) else str(o))


def has_assert(r):
    txt = "\n".join(r.get("judge_file_text", {}).values()) + "\n" + (r.get("test_cmd") or "")
    return bool(re.search(r"\bassert\b|\braise\b|sys\.exit|pytest|unittest", txt))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("prepare"); p.add_argument("--out", required=True)
    r = sp.add_parser("run"); r.add_argument("--jobs", required=True); r.add_argument("--sets", default="pilot",
        help="comma list of pilot (own patches Gemma scored 100 as reader), own, others-fail, others-pass")
    r.add_argument("--ids", help="smoke tests only: comma list of issue ids"); r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=6); r.add_argument("--step-limit", type=int, help="smoke tests only")
    z = sp.add_parser("analyze"); z.add_argument("--jobs", required=True)
    z.add_argument("--runs", nargs="+", required=True, help="name=dir, e.g. gemma=../data/lab-runs/judge-as-actor/gemma")
    z.add_argument("--boot", type=int, default=2000)
    f = sp.add_parser("finalize", help="spec addendum 3: forced final answer for runs that hit the step limit")
    f.add_argument("--jobs", required=True); f.add_argument("--src", required=True, help="run dir with runs.jsonl and trajs/")
    f.add_argument("--out", required=True); f.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    {"prepare": prepare, "run": run, "analyze": analyze, "finalize": finalize}[a.cmd](a)


if __name__ == "__main__":
    main()
