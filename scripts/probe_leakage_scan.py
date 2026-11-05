#!/usr/bin/env python3
"""Leakage scan: what in a trace/result could reveal grader output, hidden-test content or the gold patch.

Reads competition task data (problem statement, gold patch, test patch) and ATIF traces from a
scratch location; writes counts and flags only (no text).

Usage: python3 probe_leakage_scan.py <tasks.jsonl> <train_traces_root> <out.csv>
"""
import csv, glob, json, os, re, sys

tasks_path, root, out = sys.argv[1:4]
tasks = {}
for l in open(tasks_path):
    r = json.loads(l)
    tasks[r["instance_id"]] = r


def added_lines(patch, min_len=25):
    ls = []
    for l in patch.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            t = l[1:].strip()
            if len(t) >= min_len and not t.startswith(("#", '"""', "'''")):
                ls.append(t)
    return ls


def test_names(test_patch):
    plus, other = set(), set()
    for l in test_patch.splitlines():
        m = re.match(r"^([+\- ])\s*(?:async\s+)?def\s+(test_\w+)", l)
        if m:
            (plus if m.group(1) == "+" else other).add(m.group(2))
    return plus - other, plus & other  # (new names, modified/pre-existing names)


def test_files(test_patch):
    return sorted(set(re.findall(r"^\+\+\+ b/(\S+)", test_patch, re.M)))


rows = []
for d in sorted(glob.glob(os.path.join(root, "*/"))):
    t = os.path.basename(d.rstrip("/"))
    tr = json.load(open(os.path.join(d, "traces", f"trace_{t}.json")))
    res = json.load(open(os.path.join(d, "results", f"{t}.json")))
    task = tasks[t]
    steps = tr["steps"]
    user = next((s["message"] for s in steps if s.get("source") == "user"), "")
    agent_text = "\n".join((s.get("message") or "") for s in steps if s.get("source") == "agent")
    tool_args = "\n".join(json.dumps(tc.get("arguments")) for s in steps if s.get("source") == "agent" for tc in (s.get("tool_calls") or []))
    obs = "\n".join(((s.get("observation") or {}).get("content") or "") for s in steps if s.get("source") == "agent")
    ps = task["problem_statement"]
    # observations before the agent's first successful edit/write (cannot echo the agent's own change)
    first_edit = None
    agent_steps = [s_ for s_ in steps if s_.get("source") == "agent"]
    for i_, s_ in enumerate(agent_steps):
        o_ = (s_.get("observation") or {}).get("content") or ""
        for tc in s_.get("tool_calls") or []:
            if tc.get("function_name") in ("edit_file", "write_file") and '"status": "ok"' in o_:
                first_edit = i_ if first_edit is None else first_edit
    pre = agent_steps if first_edit is None else agent_steps[:first_edit]
    obs_pre = "\n".join(((s_.get("observation") or {}).get("content") or "") for s_ in pre)
    # problem statement as embedded in the prompt
    gold_added = added_lines(task["patch"])
    test_added = added_lines(task["test_patch"], min_len=20)
    test_in_ps = sum(1 for l in test_added if l in ps)
    test_in_obs = sum(1 for l in test_added if l in obs)
    test_in_agent = sum(1 for l in test_added if l in agent_text or l in tool_args)
    in_ps = sum(1 for l in gold_added if l in ps)
    in_obs = sum(1 for l in gold_added if l in obs)
    in_obs_pre = sum(1 for l in gold_added if l in obs_pre)
    in_agent = sum(1 for l in gold_added if l in agent_text or l in tool_args)
    new_names, mod_names = test_names(task["test_patch"])
    tfiles = test_files(task["test_patch"])
    def present(names, text):
        return sum(1 for n in names if n in text)
    tree_has_tfile = sum(1 for f in tfiles if f in user)
    obs_has_tfile = sum(1 for f in tfiles if f in obs)
    rows.append(dict(
        task_id=t, resolved=int(res["resolved"]),
        gold_added_lines=len(gold_added), gold_lines_in_problem_statement=in_ps,
        gold_lines_in_observations=in_obs, gold_lines_in_observations_before_first_edit=in_obs_pre, gold_lines_in_agent_text_or_args=in_agent,
        test_added_lines=len(test_added), test_lines_in_problem_statement=test_in_ps, test_lines_in_observations=test_in_obs,
        test_lines_in_agent_text_or_args=test_in_agent,
        ps_mentions_test_word=int(bool(re.search(r"\b(test_\w+|pytest|unit test|tests?/)\b", ps))),
        n_new_test_names=len(new_names), new_test_names_in_problem_statement=present(new_names, ps),
        new_test_names_in_observations=present(new_names, obs), new_test_names_in_agent_text_or_args=present(new_names, agent_text + tool_args),
        n_modified_test_names=len(mod_names), modified_test_names_in_observations=present(mod_names, obs),
        n_test_files=len(tfiles), test_files_in_prompt_tree=tree_has_tfile, test_files_in_observations=obs_has_tfile,
        result_has_test_output=int(bool(res.get("test_output"))), result_test_output_chars=len(res.get("test_output") or ""),
        result_test_exit_code=res.get("test_exit_code"),
        trace_mentions_hidden_or_grader=int(bool(re.search(r"hidden test|grader|grading|verification test", agent_text, re.I))),
        obs_contains_junit_or_resolved=int(bool(re.search(r'"resolved"\s*:|junitxml|FAIL_TO_PASS|PASS_TO_PASS', obs))),
    ))

os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
n = len(rows)
def cnt(f): return sum(1 for r in rows if f(r))
print("tasks", n)
print("tasks with gold added lines (>=25 chars):", cnt(lambda r: r["gold_added_lines"] > 0))
print("tasks where >=1 gold added line appears verbatim in problem statement:", cnt(lambda r: r["gold_lines_in_problem_statement"] > 0))
print("tasks where >=50% of gold added lines appear in problem statement:", cnt(lambda r: r["gold_added_lines"] > 0 and r["gold_lines_in_problem_statement"] / r["gold_added_lines"] >= .5))
print("tasks where >=1 gold added line appears in a tool observation:", cnt(lambda r: r["gold_lines_in_observations"] > 0))
print("  ... before the agent's first successful edit:", cnt(lambda r: r["gold_lines_in_observations_before_first_edit"] > 0))
print("tasks with hidden-test added lines (>=20 chars):", cnt(lambda r: r["test_added_lines"] > 0))
print("tasks where >=1 hidden-test added line appears verbatim in the problem statement:", cnt(lambda r: r["test_lines_in_problem_statement"] > 0))
print("tasks where >=50% of hidden-test added lines appear in the problem statement:", cnt(lambda r: r["test_added_lines"] > 0 and r["test_lines_in_problem_statement"] / r["test_added_lines"] >= .5))
print("tasks where >=1 hidden-test added line appears in a tool observation:", cnt(lambda r: r["test_lines_in_observations"] > 0))
print("tasks where >=1 hidden-test added line appears in agent text/args:", cnt(lambda r: r["test_lines_in_agent_text_or_args"] > 0))
print("tasks with new test names:", cnt(lambda r: r["n_new_test_names"] > 0))
print("tasks where a new hidden test name appears in problem statement:", cnt(lambda r: r["new_test_names_in_problem_statement"] > 0))
print("tasks where a new hidden test name appears in a tool observation:", cnt(lambda r: r["new_test_names_in_observations"] > 0))
print("tasks where a new hidden test name appears in agent text/args:", cnt(lambda r: r["new_test_names_in_agent_text_or_args"] > 0))
print("tasks where a modified (pre-existing) test name appears in observations:", cnt(lambda r: r["modified_test_names_in_observations"] > 0), "of", cnt(lambda r: r["n_modified_test_names"] > 0))
print("tasks where a hidden-test file path is in the prompt tree:", cnt(lambda r: r["test_files_in_prompt_tree"] > 0), "obs:", cnt(lambda r: r["test_files_in_observations"] > 0))
print("results with grader test_output:", cnt(lambda r: r["result_has_test_output"]))
print("traces whose agent text mentions hidden test/grader/grading:", cnt(lambda r: r["trace_mentions_hidden_or_grader"]))
print("traces whose observations contain junit/resolved/FAIL_TO_PASS:", cnt(lambda r: r["obs_contains_junit_or_resolved"]))
