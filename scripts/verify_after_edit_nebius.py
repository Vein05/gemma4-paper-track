#!/usr/bin/env python3
"""Direction-1 base rate on public SWE-agent trajectories (HF nebius/SWE-agent-trajectories, cached pages).

For each trajectory: last successful edit to a file in the final patch (SWE-agent `edit` on the
file last opened/created, or a shell write, without a lint rejection), whether any Python execution followed it (exec_after; exec_after_broad also counts any
non-navigation shell command, e.g. a repo CLI), and how the run ended (`exit_status`: plain
"submitted" = the agent chose to submit; "(exit_cost)" / "(exit_context)" etc. = forced by budget).
Writes ids, labels and counts only.

Usage: python3 verify_after_edit_nebius.py <cache_dir_with_rows_*.json> derived/verify_after_edit_nebius.csv
"""
import csv, glob, json, os, re, sys

BLOCK = re.compile(r"```(?:\w+)?\n(.*?)```", re.S)
EXEC = re.compile(r"(^|[;&|]\s*|\s)(python3?|pytest|tox|nosetests)\b|python3?\s+-m\s+(pytest|unittest)", re.M)
TEST = re.compile(r"\bpytest\b|\bunittest\b|\btox\b|\bnosetests\b")
EDIT = re.compile(r"^\s*(edit\s+\d+:\d+|create\s+\S+|insert\s+\d+|append\b)", re.M)
SHELL_WRITE = re.compile(r"sed\s+-i|>\s*\S+\.py\b|\btee\s+\S+\.py")
REJECT = re.compile(r"Your proposed edit has introduced new syntax error|Error: |usage: edit")


def command_of(text):
    blocks = BLOCK.findall(text or "")
    return blocks[-1].strip() if blocks else ""


NAV = re.compile(r"^(open|goto|scroll_up|scroll_down|search_file|search_dir|find_file|ls|cat|head|tail|grep|"
                 r"find|rm|cd|pwd|edit|create|insert|append|submit|echo|wc|which|git\s+(diff|status|log|show))\b")
FILE_OF = re.compile(r"^(open|create)\s+\"?([^\s\"]+)")


def patch_files(patch):
    return set(re.findall(r"^diff --git a/(\S+) b/", patch or "", re.M))


def row(x):
    traj = x["trajectory"]
    pfiles = patch_files(x.get("generated_patch"))
    match = lambda f: bool(f) and any(f.lstrip("./").endswith(p) or p.endswith(f.lstrip("./")) for p in pfiles)
    events = []  # (turn, kind, cmd)
    turn = 0
    cur = None
    for i, m in enumerate(traj):
        if m.get("role") != "ai":
            continue
        turn += 1
        cmd = command_of(m.get("text"))
        obs = traj[i + 1].get("text") if i + 1 < len(traj) else ""
        fm = FILE_OF.match(cmd)
        if fm:
            cur = fm.group(2)
        if EDIT.search(cmd) and not REJECT.search(obs or ""):
            events.append((turn, "edit" if match(cur) else "scratch_edit", cmd))
        elif SHELL_WRITE.search(cmd):
            events.append((turn, "edit", cmd))
        if EXEC.search(cmd) and not cmd.startswith("create"):
            events.append((turn, "test" if TEST.search(cmd) else "exec", cmd))
        elif cmd and not NAV.match(cmd) and not EDIT.search(cmd):
            events.append((turn, "other_cmd", cmd))
    edits = [e for e in events if e[1] == "edit"]
    last_edit = edits[-1][0] if edits else -1
    after = [e for e in events if e[1] in ("exec", "test") and e[0] > last_edit] if edits else []
    after_broad = [e for e in events if e[1] in ("exec", "test", "other_cmd") and e[0] > last_edit] if edits else []
    status = x.get("exit_status") or ""
    return dict(instance_id=x["instance_id"], model=x["model_name"], resolved=int(bool(x["target"])),
                patch_nonempty=int(bool((x.get("generated_patch") or "").strip())),
                exit_status=status, voluntary_submit=int(status.strip() == "submitted"),
                n_turns=turn, n_edits=len(edits), exec_after=int(bool(after)),
                exec_after_broad=int(bool(after_broad)),
                test_after=int(any(e[1] == "test" for e in after)), n_exec_after=len(after),
                n_exec_total=sum(1 for e in events if e[1] in ("exec", "test")))


def main():
    cache, out = sys.argv[1:3]
    rows = []
    for f in sorted(glob.glob(os.path.join(cache, "rows_*.json"))):
        try:
            page = json.load(open(f))["rows"]
        except (json.JSONDecodeError, KeyError):
            print(f"skipped unreadable page {os.path.basename(f)}")
            continue
        for r in page:
            rows.append(row(r.get("row", r)))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
