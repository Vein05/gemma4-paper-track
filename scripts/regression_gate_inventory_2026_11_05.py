#!/usr/bin/env python3
"""Inventory existing evidence for a regression-only Gemma approval gate.

Read-only: consumes the already-generated 2026-11-02 test-flag JSON and counts
local evaluation logs. It does not load datasets, run tests, or call a model.
Run from the repository root with Python's standard library only.
"""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "scripts/derived/test_flag_2026-11-02.json"
RUNS = ROOT / "data/mcsr-runs"
OUT = ROOT / "scripts/derived/regression_gate_inventory_2026-11-05.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = json.loads(RESULT.read_text())
per_patch = result["per_patch"]
logs = {}
for run in ("main-a", "main-b", "regrade"):
    folder = RUNS / run / "eval_logs"
    logs[run] = len(list(folder.glob("*-eval.txt"))) if folder.is_dir() else 0

summary = {
    "created_utc_date": "2026-11-05",
    "provenance": {
        "type": "read-only inventory of existing local artifacts; no new evaluation",
        "source_result": "scripts/derived/test_flag_2026-11-02.json",
        "source_analysis": "scripts/precheck/test_flag.py",
        "source_sha256": {
            "scripts/derived/test_flag_2026-11-02.json": sha256(RESULT),
            "scripts/precheck/test_flag.py": sha256(ROOT / "scripts/precheck/test_flag.py"),
        },
        "inventory_script": "scripts/regression_gate_inventory_2026_11_05.py",
        "source_discussion": "notes/fix-debate-2026-11-02.md",
        "source_spec": "spec/bug-token-precheck.md",
        "dataset_or_public_availability_assumed": False,
        "model_calls_or_test_execution": False,
    },
    "existing_result": {
        "patches": result["patches"],
        "passing_by_official_label": result["passing"],
        "failing": result["failing"],
        "Gemma_100_on_failing": result["failing_100"],
        "failing_100_flagged_for_PASS_TO_PASS_failure": sum(
            p["flag"] == 1 and p["resolved"] == 0 and p["gemma"] == 100 for p in per_patch.values()
        ),
        "all_failing_patches_flagged_for_PASS_TO_PASS_failure": result["flag_on_failing"],
        "flagged_share": result["a_share_failing_100_breaking_existing_test"],
        "unparsed_instances": result["unparsed"],
        "unparsed_ids": result["unparsed_ids"],
        "passing_patches_flagged": result["flag_on_passing"],
        "top_quarter_precision": result["b_top_quarter"],
        "increment_over_fewer_calls": result["b_flag_minus_calls_only"],
        "coverage_below_90pct_count": sum(p["coverage"] < 0.9 for p in per_patch.values()),
        "coverage_between_90pct_and_100pct_count": sum(0.9 <= p["coverage"] < 1 for p in per_patch.values()),
    },
    "local_eval_log_counts": logs,
    "base_vs_test_patch_presence": {
        "status": "unknown_from_local_artifacts",
        "reason": "The files this inventory consumes store parsed PASS_TO_PASS outcomes and coverage, not base checkout trees or test_patch diffs; dataset presence outside those consumed files is not established.",
        "minimal_cpu_check": "For diagnosis, replay the selected 17 flagged cases against exact pinned dataset rows and base snapshots, and inspect whether each test existed at base or was introduced/changed by test_patch. Treat this selected-case replay as diagnostic only. A deployable test-selection rule must never consume PASS_TO_PASS IDs or gold test_patch and must be evaluated on all frozen issues, with untouched-base and resolved-patch controls.",
    },
    "interpretation": {
        "17_of_52": "label-assisted opportunity/upper bound, not demonstrated deployable detection: the flag uses PASS_TO_PASS membership from the benchmark label and parser statuses from existing grading logs.",
        "zero_flagged_passing": "parser/grader consistency check only; it is not an independent false-positive estimate because PASS_TO_PASS is benchmark-label machinery.",
        "engineering_bottlenecks": [
            "resolve exact test identities and prove each existed at the base revision rather than being introduced by test_patch",
            "missing/unparsed results remain unresolved and are never counted as defect detections; operational deferral is reported separately",
            "measure false positives and test runtime on resolved patches plus untouched-base controls",
            "evaluate caught failing 100s on held-out instances before claiming a 20-30% reduction in false approvals",
        ],
    },
}
OUT.write_text(json.dumps(summary, indent=2) + "\n")
print(OUT.relative_to(ROOT))
