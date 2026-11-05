#!/usr/bin/env python3
"""Three counts in the paper that had no summary file: Gemma's own reproduction scripts (Section 3.3), the sandbox
problem (Section 5) and the grading check (Section 5). No model calls.

Reproduction script: as in own_script_gate.py, the last script Gemma ran, leaving out scripts that edit the source
(fix_*.py, apply_*.py, ...), is one its patch adds. Ended without error: that run's return code is 0.
Sandbox problem: an observation in the run shows ModuleNotFoundError or ImportError.
Usage (from scripts/): python3 paper_counts.py > derived/paper_counts_2026-11-05.json
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SCRIPT_RUN = r"\bpython3?\s+((?!-m\b|-c\b)[\w./-]+\.py)"
EDITOR = re.compile(r"^(fix|modify|apply|patch|update|edit|change|replace|rewrite)", re.I)
IMPORT_ERROR = re.compile(r"ModuleNotFoundError|ImportError")


def added_scripts(patch):
    new = [b for b in re.split(r"(?m)^(?=diff --git )", patch or "") if re.search(r"(?m)^new file mode", b.split("\n@@", 1)[0])]
    return {os.path.basename(re.match(r"diff --git a/(\S+) b/", b).group(1)) for b in new}


def script_ended_clean(t):
    """None if the run's last non-editing script is not one the patch adds, else whether it returned 0."""
    last = None
    for i, m in enumerate(t["messages"]):
        if m["role"] == "assistant":
            bash = re.findall(r"```bash\n(.*?)```", m["content"], re.S)
            names = [os.path.basename(s) for s in re.findall(SCRIPT_RUN, bash[-1])] if bash else []
            names = [n for n in names if not EDITOR.search(n)]
            if names:
                last = i, names[-1]
    if last is None or last[1] not in added_scripts(t["model_patch"]):
        return None
    rc = re.search(r"<returncode>(-?\d+)</returncode>", t["messages"][last[0] + 1]["content"])
    return rc is not None and rc.group(1) == "0"


def main():
    runs = {}
    for r in ("main-a", "main-b"):
        d = os.path.join(ROOT, "data", "mcsr-runs", r, "trajs")
        for f in sorted(os.listdir(d)):
            t = json.load(open(os.path.join(d, f)))
            runs[t["instance_id"]] = t
    meta = [json.loads(l) for l in open(os.path.join(ROOT, "data", "lab-runs", "existing-test-gate", "meta.jsonl"))]
    gemma = [m for m in meta if m["writer"] == "gemma-4-31b"]
    failing = [m for m in gemma if m["y"] == 0]
    clean = [script_ended_clean(runs[m["iid"]]) for m in failing]

    def problem(iid):
        return any(IMPORT_ERROR.search(m["content"]) for m in runs[iid]["messages"] if m["role"] == "user")

    def stamp(rows):
        fails = [m for m in rows if m["y"] == 0]
        return dict(scored_100=sum(m["gemma"] == 100 for m in fails), failing=len(fails))

    with_problem = [m for m in gemma if problem(m["iid"])]
    without = [m for m in gemma if not problem(m["iid"])]
    check = [json.loads(l) for l in open(os.path.join(ROOT, "data", "mcsr-runs", "validate", "val_gpt-oss-120b.jsonl"))]
    missed = [r for r in check if bool(r["resolved"]) != bool(r["official"])]
    print(json.dumps(dict(
        reproduction_script=dict(failing_patches=len(failing), ran_own_script=sum(c is not None for c in clean),
                                 ended_without_error=sum(c is True for c in clean)),
        sandbox_problem=dict(patches=len(gemma), runs_with_problem=len(with_problem), with_problem=stamp(with_problem),
                             without_problem=stamp(without)),
        grading_check=dict(patches=len(check), official_label=len(check) - len(missed),
                           misses_official_pass_graded_fail=sum(bool(r["official"]) and not r["resolved"] for r in missed)),
    ), indent=1))


if __name__ == "__main__":
    main()
