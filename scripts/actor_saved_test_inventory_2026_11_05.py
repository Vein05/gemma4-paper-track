#!/usr/bin/env python3
"""CPU-only inventory of saved Gemma judge-as-actor test artifacts.

Reads local jobs/runs JSONL only. Does not replay tests, invoke models, or read gold labels
into any deployable generation. Run from the repository root:
  python3 scripts/actor_saved_test_inventory_2026_11_05.py
"""
import json
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/lab-runs/judge-as-actor"
OUT = ROOT / "scripts/derived/actor_saved_test_inventory_2026-11-05.json"
ACTORS = ("gemma", "gptoss", "gptoss-rerun", "gptoss-final")


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    jobs = {x["pid"]: x for x in read_jsonl(DATA / "jobs.jsonl")}
    # Primary denominator is the 133 Gemma-authored patches stamped 100 by Gemma as reader.
    cohort = {p: j for p, j in jobs.items() if j.get("set") == "own" and j.get("stamped")}
    runs_by_actor = {}
    for actor in ACTORS:
        runs_by_actor[actor] = read_jsonl(DATA / actor / "runs.jsonl")

    # Saved local test outcomes are recorded on Gemma actor rows. Keep first row per pid.
    rows = {}
    for r in runs_by_actor["gemma"]:
        if r.get("pid") in cohort:
            rows.setdefault(r["pid"], r)

    by_label = defaultdict(Counter)
    source_files = Counter()
    filename_lengths = []
    absent_cmd = []
    cmd_without_saved_file = []
    missing_assets = []
    with_error_markers = []
    without_error_markers = []
    replay_manifest = []
    unique_contents = set()
    file_inventory_by_actor = {}
    for actor, actor_rows in runs_by_actor.items():
        actor_occurrences = Counter()
        actor_pairs = set()
        actor_caps = []
        for run_row in actor_rows:
            for fname, body in (run_row.get("judge_file_text") or {}).items():
                actor_occurrences[fname] += 1
                actor_pairs.add((fname, body))
                if len(body) >= 20000:
                    actor_caps.append({"pid": run_row.get("pid"), "name": fname, "length": len(body)})
        file_inventory_by_actor[actor] = {"rows_with_saved_files": sum(bool(x.get("judge_file_text")) for x in actor_rows), "source_file_occurrences": sum(actor_occurrences.values()), "unique_names": len(actor_occurrences), "unique_name_and_content_pairs": len(actor_pairs), "contents_at_or_over_20000_chars": len(actor_caps), "contents_exactly_20000_chars": [x for x in actor_caps if x["length"] == 20000]}
    categories = Counter()
    for pid, job in cohort.items():
        r = rows.get(pid, {})
        y = int(job["y"])
        label = "passing" if y else "failing"
        rv, ap = r.get("test_reverted") or {}, r.get("test_applied") or {}
        files = r.get("judge_file_text") or {}
        saved_names = sorted(files)
        by_label[label]["total"] += 1
        by_label[label]["actor_row"] += bool(r)
        by_label[label]["saved_source_count"] += len(saved_names)
        by_label[label]["command_present"] += bool(r.get("test_cmd"))
        by_label[label]["applied_pass"] += ap.get("passes") is True
        by_label[label]["applied_fail"] += ap.get("passes") is False
        by_label[label]["applied_unavailable"] += ap.get("passes") is None
        by_label[label]["reverted_fail_applied_pass"] += rv.get("passes") is False and ap.get("passes") is True
        by_label[label]["reverted_fail_applied_fail"] += rv.get("passes") is False and ap.get("passes") is False
        by_label[label]["reverted_pass_applied_pass"] += rv.get("passes") is True and ap.get("passes") is True
        by_label[label]["reverted_unavailable"] += rv.get("passes") is None
        by_label[label]["with_saved_files"] += bool(saved_names)
        by_label[label]["saved_files_applied_pass"] += bool(saved_names) and ap.get("passes") is True
        by_label[label]["saved_files_applied_fail"] += bool(saved_names) and ap.get("passes") is False
        by_label[label]["saved_files_applied_unavailable"] += bool(saved_names) and ap.get("passes") is None
        by_label[label]["cmd_without_saved_files"] += bool(r.get("test_cmd") and not saved_names)
        by_label[label]["no_test_cmd"] += not bool(r.get("test_cmd"))
        for name, content in files.items():
            source_files[name] += 1
            unique_contents.add((name, content))
            filename_lengths.append((len(content), name, pid))
            if len(content) >= 20000:
                categories["content_at_cap"] += 1
        if r.get("test_cmd") and not saved_names:
            cmd_without_saved_file.append(pid)
        if not r.get("test_cmd"):
            absent_cmd.append(pid)
        # Recorded source is the only local asset inventory. Report named non-test files
        # as supporting assets; no filesystem or sandbox probing is performed.
        support = [n for n in saved_names if n != "judge_test.py" and not re.search(r"(^|/)(test|tests|verify|check|reproduce).*\.py$", n, re.I)]
        if r.get("test_cmd") and saved_names:
            # Files are saved in the JSON row, not in the host filesystem. Supporting files
            # are therefore candidate dependencies that would need reconstructing for replay.
            if support:
                missing_assets.append({"pid": pid, "files": support})
        if r.get("test_cmd") and saved_names and ap.get("passes") is False:
            # Triage only the candidate's output. These markers do not adjudicate why
            # the candidate failed; they can coexist with a real defect.
            text = str(ap.get("output", "")).lower()
            infrastructure_markers = ("modulenotfounderror", "no module named", "importerror", "no such file or directory", "command not found", "could not import", "settings are not configured", "databaseerror", "operationalerror", "connection refused", "timed out", "timeout", "permission denied", "syntaxerror")
            if any(s in text for s in infrastructure_markers):
                with_error_markers.append(pid)
            else:
                without_error_markers.append(pid)
        # Candidate was rejected by its own saved test; tentative replay list only.
        # IDs deliberately omit y / gold label.
        if r.get("test_cmd") and saved_names and ap.get("passes") is False:
            replay_manifest.append({"pid": pid, "iid": r.get("iid"), "actor_run": "gemma", "candidate_test_files": saved_names, "test_cmd": r.get("test_cmd")})

    total_failing = sum(not x["y"] for x in cohort.values())
    total_passing = sum(bool(x["y"]) for x in cohort.values())
    failing_catches = by_label["failing"]["applied_fail"]
    passing_false_rejects = by_label["passing"]["applied_fail"]
    score100_cross = {"failing": Counter(), "passing": Counter()}
    for pid, job in cohort.items():
        r = rows.get(pid, {})
        label = "passing" if int(job["y"]) else "failing"
        score = r.get("score")
        score_group = "score_100" if score == 100 else ("score_below_100" if score is not None else "score_unavailable")
        applied = (r.get("test_applied") or {}).get("passes")
        result_group = "applied_test_fail" if applied is False else ("applied_test_pass" if applied is True else "applied_test_unavailable")
        score100_cross[label][f"{score_group}__{result_group}"] += 1
    input_paths = [DATA / "jobs.jsonl"] + [DATA / a / "runs.jsonl" for a in ACTORS]
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths}
    script_path = Path(__file__).resolve()
    source_hashes[str(script_path.relative_to(ROOT))] = hashlib.sha256(script_path.read_bytes()).hexdigest()
    summary = {
        "generated_on": "2026-11-05",
        "scope": "local saved-artifact inventory; no model calls, sandbox replay, or remote execution",
        "inputs": {"sha256": source_hashes},
        "cohort": {"stamped_own_patches": len(cohort), "failing": total_failing, "passing": total_passing},
        "actor_run_counts": {a: {"rows": len(rs), "statuses": dict(Counter(x.get("status", "(missing)") for x in rs)), "scored": sum(x.get("score") is not None for x in rs)} for a, rs in runs_by_actor.items()},
        "gemma_saved_tests_by_hidden_label": {k: dict(v) for k, v in by_label.items()},
        "saved_files": {"all_actor_runs": file_inventory_by_actor, "gemma_stamped_cohort_source_file_occurrences": dict(source_files), "gemma_stamped_cohort_unique_name_and_content_pairs": len(unique_contents), "gemma_stamped_cohort_content_files_exactly_20000_chars_potentially_truncated": [{"name": n, "pid": p} for l, n, p in filename_lengths if l == 20000], "gemma_stamped_cohort_content_files_at_least_20000_chars": [{"name": n, "length": l, "pid": p} for l, n, p in filename_lengths if l >= 20000], "gemma_stamped_cohort_content_files_at_or_over_20000_chars": categories.get("content_at_cap", 0)},
        "diagnostic_classification": {"file_backed_candidate_tests_with_applied_failure": len(replay_manifest), "with_import_environment_or_other_error_markers": with_error_markers, "without_listed_error_markers": without_error_markers, "rule": "heuristic triage of candidate test_applied output only; error markers can arise from real defects, and no listed marker does not validate semantics. Neither group is replay adjudication."},
        "command_and_asset_gaps": {"command_without_saved_files_pids": cmd_without_saved_file, "missing_test_command_pids": absent_cmd, "recorded_supporting_assets_to_reconstruct": missing_assets, "note": "Saved file text is embedded in runs.jsonl. This inventory does not claim those files exist in a replay workspace."},
        "tentative_replay_manifest": replay_manifest,
        "selection_threshold_check": {
            "failing_catches": failing_catches, "failing_denominator": total_failing,
            "failing_catch_rate": round(failing_catches / total_failing, 6),
            "passing_false_rejects": passing_false_rejects, "passing_denominator": total_passing,
            "passing_false_reject_rate": round(passing_false_rejects / total_passing, 6),
            "meets_at_least_20_percent_catch_target": failing_catches / total_failing >= 0.20,
            "meets_at_most_5_percent_false_reject_target": passing_false_rejects / total_passing <= 0.05,
            "meets_both_targets": failing_catches / total_failing >= 0.20 and passing_false_rejects / total_passing <= 0.05,
            "score100_test_applied_crosstab": {k: dict(v) for k, v in score100_cross.items()},
            "interpretation": "Catch target is at least 20%; there is no upper bound. False rejects must be at most 5%. Outcomes are recorded prior runs, not fresh execution or validated deployable behavior. Missing tests count as not caught; unknown is not treated as pass/fail."
        },
        "interface_coupling_risks": ["Most saved test commands target judge_test.py; relative paths and repo imports presume /testbed cwd and the actor's environment prefix.", "Tests may depend on modules, migrations, fixtures, generated files, environment settings, or DB initialization saved alongside the main test; a command alone is insufficient.", "Tests can assert implementation details or reproduce issue text without covering intended behavior; candidate-pass is only a diagnostic.", "The actor harness applies patches and runs tests under SWE-bench image-specific dependencies; test results may not transfer to other versions or a clean CI runner."],
        "reproducible_commands": ["python3 scripts/actor_saved_test_inventory_2026_11_05.py"],
        "usable_commands_note": "The inventory command reads saved local artifacts only. To execute a prospective replay later, use the saved environment and an explicitly reviewed allowlist; no replay command is issued here.",
        "activation_fix": "scripts/judge_actor.py ACTIVATE prefixes commands with testbed conda activation because --contain hid /root/.bashrc; documented in code comments and applied to actor runs. This reduces one known import-error source but does not validate every saved test.",
        "limitations": ["No saved test was executed for this inventory.", "Gold/pass-reference replay is pending.", "Error-marker triage does not establish infrastructure cause or semantic correctness; markers can occur alongside real defects, and their absence is not validation.", "The manifest carries patch IDs and commands only, no gold labels."]
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(OUT), "cohort": summary["cohort"], "fail": summary["gemma_saved_tests_by_hidden_label"]["failing"], "pass": summary["gemma_saved_tests_by_hidden_label"]["passing"], "threshold": summary["selection_threshold_check"], "manifest_n": len(replay_manifest)}, indent=2))


if __name__ == "__main__":
    main()
