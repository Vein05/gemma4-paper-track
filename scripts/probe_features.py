#!/usr/bin/env python3
"""Per-trajectory end-state features for the knowing/doing probe (no network, no model calls).

Reads ATIF traces + result files from public dumps (kept outside this folder because they contain
competition text) and writes a table of ids, labels and counts only (no message text).

Usage:
  python3 probe_features.py rishav  <dump_root>/logs/remote/base/train  derived/features_rishav.csv
  python3 probe_features.py ns0437  <dump_root>/reference               derived/features_ns0437.csv
"""
import csv, glob, json, os, re, sys

TEST_CMD = re.compile(r"\bpytest\b|\bunittest\b|python3?\s+-m\s+pytest|\btox\b|\bnosetests\b")
PY_CMD = re.compile(r"\bpython3?\b")
PIPE_MASK = re.compile(r"\|\s*(tail|head|grep|cat|wc|tee)\b|\|\|\s*(true|echo)|;\s*echo\b")
SUMMARY = re.compile(r"\b(\d+)\s+(passed|failed|error|errors|skipped|deselected)\b|no tests ran")
FAILED_N = re.compile(r"\b(\d+)\s+(failed|error|errors)\b")
PASSED_N = re.compile(r"\b(\d+)\s+passed\b")
LIMIT = 5000

# Transparent claim rule v2 (see report). Applied to the final agent message.
# claims_success = presents work as done (DONE phrase present) AND contains no failure/hedge phrase (FAIL).
# v1 (first draft) used generic words such as "cannot"/"can't", which fire on quoted error strings; v2 drops them.
DONE = re.compile(
    r"\b(fixed|resolved|implemented|updated|added|modified|replaced|removed|changed|introduced|applied|"
    r"submitted|verified|passed|escaped|now (returns|raises|uses|handles|passes|works))\b", re.I)
FAIL = re.compile(
    r"\b(unable to|could not|couldn'?t|was not able|wasn'?t able|failed to|ran out|budget|incomplete|partially|"
    r"not (been )?(fully )?(implemented|fixed|complete(d)?|resolved|verified)|no patch|unfortunately|unsuccessful|"
    r"proposed solution|remaining tasks?)\b", re.I)


def claim_rule(msg: str) -> int:
    if not msg:
        return 0
    return int(bool(DONE.search(msg)) and not FAIL.search(msg))


def parse_obs(obs: str):
    """Return dict(status, stdout, stderr, exit, err_type) or None."""
    try:
        o = json.loads(obs)
    except Exception:
        return None
    if not isinstance(o, dict):
        return None
    if o.get("status") == "ok":
        return dict(status="ok", stdout=o.get("stdout", "") or "", stderr=o.get("stderr", "") or "",
                    exit=o.get("exit_code"), err_type=None)
    d = o.get("details") or {}
    return dict(status="error", stdout=d.get("stdout", "") or "", stderr=d.get("stderr", "") or "",
                exit=d.get("exit_code"), err_type=o.get("error_type"))


def patch_stats(patch: str):
    files = re.findall(r"^diff --git a/(\S+) b/", patch or "", re.M)
    added = sum(1 for l in (patch or "").splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in (patch or "").splitlines() if l.startswith("-") and not l.startswith("---"))
    is_test = lambda p: bool(re.search(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$", p))
    return dict(patch_chars=len(patch or ""), patch_files=len(files),
                patch_src_files=sum(1 for f in files if not is_test(f)),
                patch_test_files=sum(1 for f in files if is_test(f)),
                patch_added=added, patch_removed=removed)


def features(trace: dict, res: dict, patch: str):
    steps = trace["steps"]
    agent = [s for s in steps if s.get("source") == "agent"]
    f = dict(n_agent_steps=len(agent), n_steps_total=len(steps))
    n_calls = 0
    n_test = n_py = n_submit_ok = n_submit = n_budget_rej = 0
    last_test = None  # (step_idx, parsed, cmd)
    last_py = None
    last_submit_idx = -1
    edit_idx = []  # steps with an ok edit_file/write_file
    for i, s in enumerate(agent):
        obs = (s.get("observation") or {}).get("content") or ""
        for tc in s.get("tool_calls") or []:
            n_calls += 1
            fn = tc.get("function_name")
            args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
            p = parse_obs(obs)
            if p and p.get("err_type") == "BudgetExceeded":
                n_budget_rej += 1
            if fn == "submit_patch":
                n_submit += 1
                if p and p["status"] == "ok":
                    n_submit_ok += 1
                    last_submit_idx = i
            if fn in ("edit_file", "write_file") and p and p["status"] == "ok":
                edit_idx.append(i)
            if fn == "run_command":
                cmd = args.get("command", "") or ""
                if TEST_CMD.search(cmd):
                    n_test += 1
                    last_test = (i, p, cmd)
                elif PY_CMD.search(cmd):
                    n_py += 1
                    last_py = (i, p, cmd)
    f.update(n_tool_calls_trace=n_calls, n_test_cmds=n_test, ran_test=int(n_test > 0), n_py_cmds=n_py,
             n_submit_calls=n_submit, n_submit_ok=n_submit_ok, submitted=int(n_submit_ok > 0),
             n_budget_rejections=n_budget_rej)
    f["n_edits_after_last_submit"] = sum(1 for e in edit_idx if e > last_submit_idx) if last_submit_idx >= 0 else ""
    if last_test:
        i, p, cmd = last_test
        out = (p["stdout"] + "\n" + p["stderr"]) if p else ""
        ex = p["exit"] if p else None
        f.update(last_test_exit=ex if ex is not None else "", last_test_exit0=int(ex == 0) if ex is not None else "",
                 last_test_err_type=(p or {}).get("err_type") or "",
                 last_test_trunc=int(bool(p) and (len(p["stdout"]) >= LIMIT or len(p["stderr"]) >= LIMIT)),
                 last_test_has_summary=int(bool(SUMMARY.search(out))),
                 last_test_masked=int(bool(PIPE_MASK.search(cmd))),
                 last_test_n_failed=sum(int(m.group(1)) for m in FAILED_N.finditer(out)),
                 last_test_n_passed=sum(int(m.group(1)) for m in PASSED_N.finditer(out)),
                 last_test_steps_from_end=len(agent) - 1 - i)
        # "summary-aware" pass: some passed, none failed/errored, regardless of exit code mask
        f["last_test_summary_pass"] = int(f["last_test_n_passed"] > 0 and f["last_test_n_failed"] == 0)
    else:
        for k in ("last_test_exit", "last_test_exit0", "last_test_err_type", "last_test_trunc", "last_test_has_summary",
                  "last_test_masked", "last_test_n_failed", "last_test_n_passed", "last_test_steps_from_end",
                  "last_test_summary_pass"):
            f[k] = ""
    if last_py:
        f["last_py_exit0"] = int(last_py[1]["exit"] == 0) if last_py[1] and last_py[1]["exit"] is not None else ""
    else:
        f["last_py_exit0"] = ""
    # final message
    final = [s for s in agent if (s.get("extra") or {}).get("event_type") == "final"]
    last_msg_step = final[-1] if final else (agent[-1] if agent else {})
    msg = last_msg_step.get("message") or ""
    f["has_final_message"] = int(bool(final))
    f["final_msg_chars"] = len(msg)
    f["claims_success_rule"] = claim_rule(msg)
    # termination
    err = (res.get("error_message") or res.get("error") or "") or ""
    if "tool call budget" in err:
        term = "tool_budget"
    elif "turns budget" in err or "turn budget" in err:
        term = "turn_budget"
    elif "timeout" in err.lower():
        term = "timeout"
    elif err:
        term = "other_error"
    elif final:
        term = "final_after_submit" if n_submit_ok else "final_no_submit"
    else:
        term = "no_final"
    f["termination"] = term
    f["harness_error_class"] = ("tool_budget" if "tool call budget" in err else "turn_budget" if "turns budget" in err
                                else "timeout" if "timeout" in err.lower() else "")
    fm = trace.get("final_metrics") or {}
    f["prompt_tokens_sum"] = fm.get("total_prompt_tokens", "")
    f["completion_tokens_sum"] = fm.get("total_completion_tokens", "")
    f["n_compaction_markers"] = sum(1 for s in steps if "summar" in ((s.get("extra") or {}).get("event_type") or ""))
    f.update(patch_stats(patch))
    f["patch_nonempty"] = int(len(patch or "") > 0)
    return f, msg


def load_rishav(root):
    for d in sorted(glob.glob(os.path.join(root, "*/"))):
        t = os.path.basename(d.rstrip("/"))
        tf = os.path.join(d, "traces", f"trace_{t}.json")
        rf = os.path.join(d, "results", f"{t}.json")
        if not (os.path.exists(tf) and os.path.exists(rf)):
            continue
        res = json.load(open(rf))
        yield dict(source="rishav_base", run_id=t, task_id=t, repo=res.get("repo", "")), json.load(open(tf)), res, res.get("agent_patch") or ""


def load_ns0437(root):
    for tf in sorted(glob.glob(os.path.join(root, "**", "traces", "trace_*.json"), recursive=True)):
        rdir = os.path.dirname(os.path.dirname(tf))
        task = os.path.basename(tf)[6:-5]
        rl = os.path.join(rdir, "task_results.jsonl")
        res = json.loads(open(rl).readline()) if os.path.exists(rl) else {}
        pf = os.path.join(rdir, "patches", f"{task}.patch")
        patch = open(pf).read() if os.path.exists(pf) else ""
        exp = os.path.relpath(rdir, root).replace(os.sep, "/")
        yield dict(source="ns0437", run_id=exp, task_id=task, repo=res.get("repo", "")), json.load(open(tf)), res, patch


def main():
    kind, root, out = sys.argv[1:4]
    loader = {"rishav": load_rishav, "ns0437": load_ns0437}[kind]
    rows = []
    msgs = {}
    for meta, trace, res, patch in loader(root):
        f, msg = features(trace, res, patch)
        row = dict(meta)
        row["resolved"] = int(bool(res.get("resolved")))
        row["harness_test_exit_code"] = res.get("test_exit_code", "")
        row["harness_tool_calls"] = res.get("tool_calls", "")
        row["harness_llm_calls"] = res.get("total_llm_calls", "")
        row.update(f)
        rows.append(row)
        msgs[meta["run_id"]] = msg
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")
    # final messages are kept OUT of the project folder (they can quote competition text)
    sp = os.environ.get("PROBE_SCRATCH")
    if sp:
        json.dump(msgs, open(os.path.join(sp, f"final_msgs_{kind}.json"), "w"))


if __name__ == "__main__":
    main()
