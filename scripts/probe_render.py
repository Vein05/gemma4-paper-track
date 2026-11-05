#!/usr/bin/env python3
"""Render verdict-probe inputs from public ATIF traces (no network, no model calls).

Arms (see notes/probe-design-knowing-doing-2026-10-04.md):
  a  : issue + full trajectory + final patch            (judge sees everything the agent saw/did)
  b  : issue + final patch + last test run              (evidence anyone could read; also used by arm c)
  b+ : b + the agent's final message                    (adds the agent's own claim)
Inputs never include: results/*.json fields test_output, test_exit_code, error_message, resolved, status;
logs/*.log; the task's gold patch or test patch.

Usage:
  python3 probe_render.py stats <train_traces_root> <tasks.jsonl|-> <out.csv>     # token estimates per arm
  python3 probe_render.py show  <train_traces_root> <task_id> <arm>                # print one rendered prompt
"""
import csv, glob, json, os, re, sys

PROTECTED = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)(conftest\.py|pytest\.ini|pyproject\.toml|tox\.ini|setup\.cfg)$")
TEST_CMD = re.compile(r"\bpytest\b|\bunittest\b|python3?\s+-m\s+pytest|\btox\b|\bnosetests\b")

SYSTEM = ("You are an expert Python maintainer. You review a proposed fix for a reported issue. "
          "You cannot run code; judge from the material given.")

QUESTION = """Question: after this patch is applied, will the maintainers' hidden tests for this issue pass?
The hidden tests were written for the upstream fix. They check the behaviour the issue asks for, including exact names, parameters, messages and types, and tests that passed before must still pass. Changes to test files, conftest.py, pytest.ini, pyproject.toml, tox.ini and setup.cfg are discarded before grading; the patch shown above already omits them.
Reply with one line of JSON and nothing else:
{"verdict": "PASS" or "FAIL", "p_pass": <your probability from 0 to 1 that the hidden tests pass>}
The verdict is "PASS" if and only if p_pass is at least 0.5."""


def problem_statement(trace):
    user = next(s["message"] for s in trace["steps"] if s.get("source") == "user")
    m = re.search(r"Problem Statement:\n(.*?)\n\n## Task Budget", user, re.S)
    return m.group(1) if m else ""


def repo_name(trace):
    user = next(s["message"] for s in trace["steps"] if s.get("source") == "user")
    m = re.search(r"for repository (\S+?)\.", user)
    return m.group(1) if m else "unknown"


def effective_patch(patch):
    """Drop per-file diffs for paths the harness resets before grading."""
    parts = re.split(r"(?m)^(?=diff --git )", patch or "")
    keep, dropped = [], []
    for p in parts:
        m = re.match(r"diff --git a/(\S+) b/", p)
        if not m:
            if p.strip():
                keep.append(p)
            continue
        if PROTECTED.search(m.group(1)):
            dropped.append(m.group(1))
        else:
            keep.append(p)
    return "".join(k for k in keep), dropped


def parse_obs(obs):
    try:
        o = json.loads(obs)
    except Exception:
        return None
    if o.get("status") == "ok":
        return dict(ok=True, stdout=o.get("stdout", ""), stderr=o.get("stderr", ""), exit=o.get("exit_code"))
    d = o.get("details") or {}
    return dict(ok=False, stdout=d.get("stdout", ""), stderr=d.get("stderr", ""), exit=d.get("exit_code"), err=o.get("error_type"))


def last_test_run(trace):
    last = None
    for s in trace["steps"]:
        if s.get("source") != "agent":
            continue
        obs = (s.get("observation") or {}).get("content") or ""
        for tc in s.get("tool_calls") or []:
            if tc.get("function_name") == "run_command":
                cmd = (tc.get("arguments") or {}).get("command", "")
                if TEST_CMD.search(cmd):
                    p = parse_obs(obs)
                    if p:
                        last = (cmd, p)
    return last


def fmt_test_run(last):
    if not last:
        return "The agent did not run any test command."
    cmd, p = last
    out = p["stdout"] + (("\n[stderr]\n" + p["stderr"]) if p["stderr"] else "")
    cut = len(p["stdout"]) >= 5000 or len(p["stderr"]) >= 5000
    note = "\nNote: the harness cuts each stream at 5000 characters without a marker; this output may be cut." if cut else ""
    return f"Command: {cmd}\nExit code: {p['exit']}\nOutput:\n{out}{note}"


def final_patch(res_patch):
    p, dropped = effective_patch(res_patch)
    return p if p.strip() else "(empty patch)", dropped


def render_b(trace, agent_patch, plus=False):
    ps = problem_statement(trace)
    patch, _ = final_patch(agent_patch)
    s = (f"A user reported the issue below for the repository {repo_name(trace)}. A coding agent produced the patch below.\n\n"
         f"<issue>\n{ps}\n</issue>\n\n<patch>\n{patch}\n</patch>\n\n<last_test_run>\n{fmt_test_run(last_test_run(trace))}\n</last_test_run>\n\n")
    if plus:
        fin = [x for x in trace["steps"] if x.get("source") == "agent" and (x.get("extra") or {}).get("event_type") == "final"]
        s += f"<agent_final_message>\n{fin[-1]['message'] if fin else '(none)'}\n</agent_final_message>\n\n"
    return s + QUESTION


def render_steps(trace, obs_cap, arg_cap):
    out = []
    n = 0
    for s in trace["steps"]:
        src = s.get("source")
        if src in ("user",) or (src == "system" and (s.get("extra") or {}).get("event_type") == "system_instruction"):
            continue
        if src == "system":
            out.append(f"[harness] {(s.get('message') or '')[:600]}")
            continue
        n += 1
        msg = s.get("message") or ""
        if msg:
            out.append(f"[step {n}] AGENT: {msg}")
        obs = (s.get("observation") or {}).get("content") or ""
        for tc in s.get("tool_calls") or []:
            a = json.dumps(tc.get("arguments"), ensure_ascii=False)
            out.append(f"[step {n}] TOOL CALL {tc.get('function_name')}: {a[:arg_cap]}{' ...[cut]' if len(a) > arg_cap else ''}")
        if obs:
            out.append(f"[step {n}] TOOL RESULT: {obs[:obs_cap]}{' ...[cut]' if len(obs) > obs_cap else ''}")
    return "\n".join(out)


def render_a(trace, agent_patch, obs_cap=5000, arg_cap=100000, strip_budget=False):
    ps = problem_statement(trace)
    patch, _ = final_patch(agent_patch)
    steps = render_steps(trace, obs_cap, arg_cap)
    if strip_budget:
        steps = re.sub(r', ?"budget_warning": "[^"]*"', "", steps)
    return (f"Below is the complete record of a coding agent working on an issue in the repository {repo_name(trace)}: "
            f"the issue, every step (reasoning, tool calls, tool results), and the final patch.\n\n"
            f"<issue>\n{ps}\n</issue>\n\n<transcript>\n{steps}\n</transcript>\n\n<patch>\n{patch}\n</patch>\n\n{QUESTION}")


def parse_verdict(text):
    """Return (p_pass or None, verdict or None, ok flag)."""
    if not text:
        return None, None, False
    m = re.search(r"\{[^{}]*\}", text, re.S)
    p = v = None
    if m:
        try:
            o = json.loads(m.group(0))
            p = float(o.get("p_pass")) if o.get("p_pass") is not None else None
            v = str(o.get("verdict", "")).upper() or None
        except Exception:
            pass
    if v not in ("PASS", "FAIL"):
        mv = re.findall(r"\b(PASS|FAIL)\b", text)
        v = mv[0] if mv else None
    if p is not None:
        p = min(1.0, max(0.0, p))
    return p, v, (p is not None and v in ("PASS", "FAIL"))


def load(root):
    for d in sorted(glob.glob(os.path.join(root, "*/"))):
        t = os.path.basename(d.rstrip("/"))
        tr = json.load(open(os.path.join(d, "traces", f"trace_{t}.json")))
        res = json.load(open(os.path.join(d, "results", f"{t}.json")))
        yield t, tr, res.get("agent_patch") or "", int(bool(res.get("resolved")))


def main():
    cmd = sys.argv[1]
    if cmd == "show":
        root, tid, arm = sys.argv[2:5]
        for t, tr, patch, y in load(root):
            if t == tid:
                f = {"a": render_a, "b": render_b, "b+": lambda x, p: render_b(x, p, plus=True)}[arm]
                print(SYSTEM + "\n\n---\n\n" + f(tr, patch))
        return
    root, _, out = sys.argv[2:5]
    rows = []
    for t, tr, patch, y in load(root):
        b = render_b(tr, patch); bp = render_b(tr, patch, plus=True)
        a_raw = render_a(tr, patch, obs_cap=10**9); a_agentview = render_a(tr, patch, obs_cap=5000)
        a_cap = render_a(tr, patch, obs_cap=2000, arg_cap=1000)
        rows.append(dict(task_id=t, resolved=y, patch_nonempty=int(bool(patch.strip())),
                         chars_b=len(b), chars_bplus=len(bp), chars_a_raw=len(a_raw), chars_a_agentview=len(a_agentview), chars_a_cap=len(a_cap),
                         chars_sys=len(SYSTEM)))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("wrote", len(rows), out)


if __name__ == "__main__":
    main()
