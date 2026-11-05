#!/usr/bin/env python3
"""Read-only retrospective summary; see spec/repair-trace-audit-2026-11-05.md.

Run from any directory. Prints JSON; redirect to a separate derived artifact.
No model calls, network access, grading, or changes to original run files.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/lab-runs/test-repair"
GATE = ROOT / "data/lab-runs/existing-test-gate"


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def keyed(items, key):
    result = {r[key]: r for r in items}
    assert len(result) == len(items), f"Duplicate {key}"
    return result


def paired_counts(left, right, population):
    wins = sum(left[p] > right[p] for p in population)
    losses = sum(left[p] < right[p] for p in population)
    n = wins + losses
    one_sided = sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n if n else 1.0
    tail = sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2**n if n else 1.0
    return dict(left_only=wins, right_only=losses, one_sided_p=one_sided,
                two_sided_p=min(1.0, 2 * tail))


def main():
    meta = keyed([r for r in rows(GATE / "meta.jsonl") if r["writer"] == "gemma-4-31b"], "pid")
    gate = keyed([r for r in rows(GATE / "runs.jsonl")
                  if r.get("kind") == "patch" and r.get("writer") == "gemma-4-31b"], "pid")
    blocked = {p for p, r in gate.items() if r.get("decision") == "block"}
    before = {p: int(m["y"]) for p, m in meta.items()}
    stamped = [p for p, m in meta.items() if m["gemma"] == 100]
    stamped_fail = [p for p in stamped if not before[p]]
    blocked_fail = [p for p in blocked if not before[p]]
    original = json.loads((ROOT / "scripts/derived/test_repair_2026-11-05.json").read_text())
    arms, outcomes, per_run, sources = {}, {}, [], set()
    for arm in ("tests", "review"):
        preds = keyed(rows(RUN / arm / "preds.jsonl"), "instance_id")
        labels = keyed(rows(RUN / arm / "labels.jsonl"), "instance_id")
        outcomes[arm] = dict(before)
        groups = collections.defaultdict(list)
        arm_records = []
        sources.update([RUN / arm / "preds.jsonl", RUN / arm / "labels.jsonl"])
        for iid, pred in sorted(preds.items()):
            p = pred["pid"]
            assert p in blocked
            trace_path = RUN / arm / "trajs" / f"{iid}.json"
            trace = json.loads(trace_path.read_text())
            sources.add(trace_path)
            assert all(trace[k] == pred[k] for k in ("pid", "exit_status", "n_calls", "model_patch"))
            label = labels.get(iid, {}).get("resolved")
            outcome = before[p] if label is None else int(bool(label))
            outcomes[arm][p] = outcome
            group = f"{before[p]}->{outcome}"
            groups[group].append(pred["n_calls"])
            record = dict(arm=arm, instance_id=iid, pid=p, original_grade=before[p],
                          final_grade=outcome, stamped=p in stamped, n_calls=pred["n_calls"],
                          exit_status=pred["exit_status"], fallback_to_original=label is None,
                          format_errors=sum("Please always provide EXACTLY ONE action" in m["content"]
                                            for m in trace["messages"] if m["role"] == "user"),
                          trace=str(trace_path.relative_to(ROOT)))
            arm_records.append(record)
        assert len(arm_records) == len(blocked) == 35
        per_run.extend(arm_records)
        r = outcomes[arm]
        repairs = sum(not before[p] and r[p] for p in meta)
        harms = sum(before[p] and not r[p] for p in meta)
        stamped_repairs = sum(r[p] for p in stamped_fail)
        stamped_harms = sum(before[p] and not r[p] for p in stamped)
        assert (repairs, harms, stamped_repairs, sum(r.values())) == (
            original[arm]["blocked_failing_now_passing"], original[arm]["blocked_passing_now_failing"],
            original[arm]["stamped_failing_now_passing"], original[arm]["resolved_after"])
        arms[arm] = dict(repairs=repairs, harms=harms, resolved=sum(r.values()),
                         net_resolved_gain=repairs-harms, stamped_repairs=stamped_repairs,
                         stamped_repair_rate=stamped_repairs/len(stamped_fail), stamped_harms=stamped_harms,
                         stamped_passes_after=sum(r[p] for p in stamped),
                         stamped_failures_after=sum(not r[p] for p in stamped),
                         total_calls=sum(x["n_calls"] for x in arm_records),
                         format_errors=sum(x["format_errors"] for x in arm_records),
                         runs_with_format_errors=sum(x["format_errors"] > 0 for x in arm_records),
                         status_counts=dict(collections.Counter(x["exit_status"] for x in arm_records)),
                         calls_by_transition={k: dict(n=len(v), median=statistics.median(v),
                                                     minimum=min(v), maximum=max(v))
                                              for k, v in sorted(groups.items())})
    sources.update([GATE / "meta.jsonl", GATE / "runs.jsonl", RUN / "jobs.jsonl",
                    ROOT / "scripts/derived/test_repair_2026-11-05.json"])
    tests_failed = [r for r in per_run if r["arm"] == "tests" and r["original_grade"] == 0
                    and r["final_grade"] == 0]
    submitted_failed = [r["n_calls"] for r in tests_failed if r["exit_status"] == "Submitted"]
    report = dict(
        date="2026-11-05", status="retrospective, descriptive; no new inference or execution grading",
        populations=dict(all=len(meta), stamped=len(stamped), stamped_failing=len(stamped_fail),
                         blocked=len(blocked), blocked_failing=len(blocked_fail)),
        arms=arms,
        comparisons=dict(
            prespecified_blocked_failing=paired_counts(outcomes["tests"], outcomes["review"], blocked_fail),
            exploratory_all_outcomes=paired_counts(outcomes["tests"], outcomes["review"], list(meta)),
            exploratory_stamped_outcomes=paired_counts(outcomes["tests"], outcomes["review"], stamped)),
        remaining_feedback_failures=dict(n=len(tests_failed), submitted=len(submitted_failed),
                                         submitted_calls_min=min(submitted_failed),
                                         submitted_calls_max=max(submitted_failed),
                                         submitted_calls_median=statistics.median(submitted_failed),
                                         step_limit_exits=sum(r["exit_status"] == "LimitsExceeded"
                                                              for r in tests_failed)),
        stamped_failure_gate_decisions=dict(collections.Counter(
            gate[p].get("decision", "no_check") for p in stamped_fail)),
        per_run=per_run,
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(sources)})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
