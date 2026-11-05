#!/usr/bin/env python3
"""Wrong-file failures in the Gemma traces: had the agent seen the right file before editing elsewhere?

Inputs: the rishav ATIF dump (competition-task traces, session scratchpad) and the public GraphLoc-129
labels (gold files and gold symbols per task, Apache-2.0). Writes ids, flags and step indices only.
No network, no model calls.

Per run (step indices count agent steps from 0):
  outcome            resolved / right_file (edits a gold file, unresolved) / wrong_file / empty
  issue_names_file   the task prompt contains a gold file path or its module name
  issue_names_sym    the task prompt contains a gold symbol name
  first_edit         first successful edit to a non-test source file
  path_seen          first step whose observation contains a gold file path (e.g. grep/ls output)
  file_read          first step that reads a gold file (read_file, or cat/sed/head/grep/nl on it)
  def_seen           first step whose observation contains "def <gold symbol>" or "class <gold symbol>"
  agent_named        first step whose agent message names a gold file or gold symbol
  gold_edited        the agent edited a gold file at some point (final patch may not contain it)

Usage: python3 wrong_file_trace.py <rishav>/logs/remote/base/train <graphloc129_labels.jsonl> derived/wrong_file_rishav.csv
"""
import csv, glob, json, os, re, sys

READ_CMD = re.compile(r"\b(cat|sed|head|tail|grep|nl|less|awk)\b")
IS_TEST = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$")


def load_labels(path):
    out = {}
    for line in open(path):
        x = json.loads(line)
        syms = {s["id"].split(".")[-1] for s in x.get("gold_symbols", [])}
        out[x["instance_id"]] = dict(files=set(x.get("gold_files", [])), syms={s for s in syms if len(s) > 3})
    return out


def text(v):
    return v if isinstance(v, str) else json.dumps(v) if v is not None else ""


def first(steps, pred):
    for i, s in enumerate(steps):
        if pred(i, s):
            return i
    return ""


def analyse(trace, res, gold):
    files, syms = gold["files"], gold["syms"]
    mods = {f[:-3].replace("/", ".") for f in files if f.endswith(".py")}
    prompt = " ".join(text(s.get("message")) for s in trace["steps"] if s.get("source") == "user")
    agent = [s for s in trace["steps"] if s.get("source") == "agent"]

    def obs(s):
        return text((s.get("observation") or {}).get("content"))

    def calls(s):
        return [(tc.get("function_name"), tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {})
                for tc in s.get("tool_calls") or []]

    def hits_file(p):
        p = (p or "").lstrip("./")
        return any(p == f or p.endswith("/" + f) or f.endswith("/" + p) and p for f in files)

    def reads_gold(i, s):
        for fn, a in calls(s):
            if fn == "read_file" and hits_file(a.get("filepath")):
                return True
            if fn == "run_command":
                c = a.get("command", "") or ""
                if READ_CMD.search(c) and any(f in c for f in files):
                    return True
        return False

    def edits(s, gold_only):
        for fn, a in calls(s):
            if fn in ("edit_file", "write_file"):
                p = (a.get("filepath") or "").lstrip("./")
                if gold_only and hits_file(p):
                    return True
                if not gold_only and p.endswith(".py") and not IS_TEST.search(p):
                    return True
        return False

    patch = res.get("agent_patch") or ""
    pfiles = {f for f in re.findall(r"^diff --git a/(\S+) b/", patch, re.M) if not IS_TEST.search(f)}
    if res.get("resolved"):
        outcome = "resolved"
    elif not patch.strip():
        outcome = "empty"
    elif pfiles & files:
        outcome = "right_file"
    else:
        outcome = "wrong_file"
    sym_def = [re.compile(rf"\b(def|class)\s+{re.escape(n)}\b") for n in syms]
    return dict(
        outcome=outcome, n_gold_files=len(files), n_agent_steps=len(agent),
        issue_names_file=int(any(f in prompt for f in files) or any(m in prompt for m in mods)),
        issue_names_sym=int(any(re.search(rf"\b{re.escape(n)}\b", prompt) for n in syms)),
        first_edit=first(agent, lambda i, s: edits(s, False)),
        path_seen=first(agent, lambda i, s: any(f in obs(s) for f in files)),
        file_read=first(agent, reads_gold),
        def_seen=first(agent, lambda i, s: any(p.search(obs(s)) for p in sym_def)),
        agent_named=first(agent, lambda i, s: any(f in text(s.get("message")) for f in files)
                          or any(re.search(rf"\b{re.escape(n)}\b", text(s.get("message"))) for n in syms)),
        gold_edited=int(any(edits(s, True) for s in agent)),
    )


def main():
    root, labels, out = sys.argv[1:4]
    gold = load_labels(labels)
    rows = []
    for d in sorted(glob.glob(os.path.join(root, "*/"))):
        t = os.path.basename(d.rstrip("/"))
        tf, rf = os.path.join(d, "traces", f"trace_{t}.json"), os.path.join(d, "results", f"{t}.json")
        if not (os.path.exists(tf) and os.path.exists(rf)) or t not in gold:
            continue
        r = dict(task_id=t)
        r.update(analyse(json.load(open(tf)), json.load(open(rf)), gold[t]))
        rows.append(r)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
