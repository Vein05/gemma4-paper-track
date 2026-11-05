#!/usr/bin/env python3
"""Base rate for direction 1 (verification receipts): did the agent execute anything after its last edit?

Reads the rishav ATIF dump (competition-task traces, kept in the session scratchpad) and writes ids,
labels and counts only. No network, no model calls.

Per trajectory:
  last_edit      index of the last successful edit (edit_file/write_file ok, or a run_command that writes
                 a .py file: sed -i, redirect, tee, patch, git apply, python heredoc writing a file)
  exec_after     any run_command after last_edit that runs Python code (python/pytest/unittest/tox)
  test_after     a test command after last_edit
  touch_after    an execution after last_edit whose command names the changed module or a file in the patch
                 (string proxy for "exercised the changed code"; real coverage is not in the traces)
  last_exec_ok   exit code 0 of the last execution after last_edit (blank if none)

Usage: python3 verify_after_edit.py <dump_root>/logs/remote/base/train derived/verify_after_edit_rishav.csv
"""
import csv, glob, json, os, re, sys

EXEC = re.compile(r"\bpython3?\b|\bpytest\b|\bunittest\b|\btox\b|\bnosetests\b")
TEST = re.compile(r"\bpytest\b|\bunittest\b|python3?\s+-m\s+pytest|\btox\b|\bnosetests\b")
SHELL_WRITE = re.compile(r"sed\s+-i|>\s*\S+\.py\b|\btee\s+\S+\.py|\bpatch\b\s|git\s+apply|open\([^)]*['\"]w")
EDIT_FNS = ("edit_file", "write_file", "create_file", "str_replace", "apply_patch")


def parse_obs(obs):
    try:
        o = json.loads(obs)
    except Exception:
        return None
    if not isinstance(o, dict):
        return None
    if o.get("status") == "ok":
        return dict(ok=True, exit=o.get("exit_code"))
    d = o.get("details") or {}
    return dict(ok=False, exit=d.get("exit_code"), err=o.get("error_type"))


def patch_names(patch):
    files = re.findall(r"^diff --git a/(\S+) b/", patch or "", re.M)
    names = set()
    for f in files:
        base = os.path.basename(f)[:-3] if f.endswith(".py") else os.path.basename(f)
        names.add(base)
        names.add(f)
        names.add(f[:-3].replace("/", ".") if f.endswith(".py") else f)
    return {n for n in names if n and n not in ("__init__", "utils", "main")}


def row_for(trace, res, patch):
    agent = [s for s in trace["steps"] if s.get("source") == "agent"]
    events = []  # (idx, kind, cmd, parsed)
    for i, s in enumerate(agent):
        obs = (s.get("observation") or {}).get("content") or ""
        p = parse_obs(obs)
        for tc in s.get("tool_calls") or []:
            fn = tc.get("function_name")
            args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
            if fn in EDIT_FNS and p and p["ok"]:
                events.append((i, "edit", "", p))
            elif fn == "run_command":
                cmd = args.get("command", "") or ""
                if SHELL_WRITE.search(cmd) and p and p.get("exit") == 0:
                    events.append((i, "edit", cmd, p))
                if EXEC.search(cmd):
                    events.append((i, "test" if TEST.search(cmd) else "exec", cmd, p))
    edits = [e for e in events if e[1] == "edit"]
    last_edit = edits[-1][0] if edits else -1
    after = [e for e in events if e[1] in ("exec", "test") and e[0] > last_edit] if edits else []
    names = patch_names(patch)
    touch = [e for e in after if any(n in e[2] for n in names)]
    last = after[-1] if after else None
    return dict(n_edits=len(edits), last_edit_steps_from_end=(len(agent) - 1 - last_edit) if edits else "",
                exec_after=int(bool(after)), test_after=int(any(e[1] == "test" for e in after)),
                touch_after=int(bool(touch)), n_exec_after=len(after),
                last_exec_ok=(int(last[3] is not None and last[3].get("exit") == 0) if last else ""),
                n_exec_total=sum(1 for e in events if e[1] in ("exec", "test")))


def main():
    root, out = sys.argv[1:3]
    rows = []
    for d in sorted(glob.glob(os.path.join(root, "*/"))):
        t = os.path.basename(d.rstrip("/"))
        tf, rf = os.path.join(d, "traces", f"trace_{t}.json"), os.path.join(d, "results", f"{t}.json")
        if not (os.path.exists(tf) and os.path.exists(rf)):
            continue
        res = json.load(open(rf))
        patch = res.get("agent_patch") or ""
        err = res.get("error_message") or res.get("error") or ""
        r = dict(task_id=t, resolved=int(bool(res.get("resolved"))), patch_nonempty=int(bool(patch)),
                 at_tool_cap=int("tool call budget" in err))
        r.update(row_for(json.load(open(tf)), res, patch))
        rows.append(r)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
