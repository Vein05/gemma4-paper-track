#!/usr/bin/env python3
"""Build a normalized table of Gemma 4 31B agent patches + official SWE-bench labels
from six public HF datasets by n-pelleriti (SWE-bench Verified Mini, 50 tasks).

Usage:
    python scripts/gemma_own_attempts.py --cache <dir> [--out data/public/gemma4-own-attempts]
                                         [--no-download]

Downloads only the small files needed (README, manifest, preds, reports, task JSONs,
per-instance report.json / patch.diff / run_instance.log); skips trajectories and logs.
Writes attempts.jsonl and summary.json to --out. Needs `huggingface_hub`.

Label rules (see README.md in the output dir):
  * non-sweagent datasets: resolved = per-instance SWE-bench report.json `resolved`
    (swebench_eval/<iid>/report.json); cross-checked against the run JSONL `correct`.
    Non-empty patch but no report.json -> status eval_error, resolved null
    (run_instance.log says why, e.g. patch_apply_failed).
  * sweagent dataset: resolved from official_reports/*.json (resolved_ids / unresolved_ids);
    error_ids -> eval_error, empty_patch_ids -> empty_patch.
  * empty patch -> status empty_patch, resolved false (as the source scored it), usable false.
  * usable = non-empty patch AND an evaluator-produced resolved label.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

USER = "n-pelleriti"
DATASETS = [
    # (dataset id, harness)
    ("alphadiana-sweagent-gemma4-directllm-20260727", "sweagent"),
    ("alphadiana-swe-mini-opencode-gemma4-20260602-818023", "opencode"),
    ("alphadiana-swe-mini-opencode-gemma4-20260725-v04", "opencode"),
    ("alphadiana-swe-mini-openclaw-gemma4-20260724-k9q7", "openclaw"),
    ("alphadiana-swe-mini-zeroclaw-gemma4-20260724-r6m2", "zeroclaw"),
    ("alphadiana-swe-mini-direct-gemma4-20260725-m8v4", "direct_noharness"),
]
SWEAGENT_ID = DATASETS[0][0]
PATTERNS_COMMON = ["README.md", "manifest.json", "metadata/*"]
PATTERNS_AGENT = [
    "results/*.jsonl",
    "results/*/tasks/*.json",
    "results/*/run_manifest.json",
    "results/*/artifacts/*/workspace/swebench_eval/*/report.json",
    "results/*/artifacts/*/workspace/swebench_eval/*/patch.diff",
    "results/*/artifacts/*/workspace/swebench_eval/*/run_instance.log",
]
PATTERNS_SWEAGENT = [
    "official_reports/*",
    "sweagent_results/*/preds.json",
    "sweagent_results/*/*.pred",
    "sweagent_results/*/*.patch",
    "logs/*official-eval.log",
]


def download(cache, shas):
    from huggingface_hub import HfApi, snapshot_download

    api = HfApi()
    for ds, _ in DATASETS:
        repo = f"{USER}/{ds}"
        shas[ds] = api.dataset_info(repo).sha
        pats = PATTERNS_COMMON + (PATTERNS_SWEAGENT if ds == SWEAGENT_ID else PATTERNS_AGENT)
        snapshot_download(
            repo, repo_type="dataset", revision=shas[ds],
            local_dir=os.path.join(cache, ds), allow_patterns=pats,
        )


def read(p):
    with open(p, errors="replace") as f:
        return f.read()


def norm_patch(p):
    return p if p and p.strip() else None


def row(ds, run, harness, iid, patch, resolved, status, label_source, patch_source, detail=None):
    patch = norm_patch(patch)
    return {
        "dataset": f"{USER}/{ds}",
        "run": run,
        "instance_id": iid,
        "harness": harness,
        "patch": patch,
        "resolved": resolved,
        "status": status,
        "label_source": label_source,
        "patch_source": patch_source,
        "status_detail": detail,
        "usable": bool(patch) and status == "valid_scored" and resolved is not None,
    }


def sweagent_rows(cache, ds, harness, warn):
    root = os.path.join(cache, ds)
    rows = []
    for pj in sorted(glob.glob(os.path.join(root, "sweagent_results", "*", "preds.json"))):
        run = os.path.basename(os.path.dirname(pj))
        preds = json.load(open(pj))
        rel_preds = os.path.relpath(pj, root)
        rep_path = glob.glob(os.path.join(root, "official_reports", f"{run}.{run}.json"))
        if not rep_path:
            warn(f"{ds}/{run}: no official report")
            continue
        rep = json.load(open(rep_path[0]))
        rel_rep = os.path.relpath(rep_path[0], root)
        resolved, unresolved = set(rep["resolved_ids"]), set(rep["unresolved_ids"])
        errors, empty = set(rep["error_ids"]), set(rep["empty_patch_ids"])
        eval_log = glob.glob(os.path.join(root, "logs", f"{run}.official-eval.log"))
        for iid in sorted(preds):
            patch = norm_patch(preds[iid].get("model_patch"))
            # cross-check per-instance .pred
            pp = os.path.join(os.path.dirname(pj), iid, f"{iid}.pred")
            if os.path.exists(pp):
                q = norm_patch(json.load(open(pp)).get("model_patch"))
                if q != patch:
                    warn(f"{run}/{iid}: .pred differs from preds.json")
            detail = None
            if iid in resolved:
                st, res = "valid_scored", True
            elif iid in unresolved:
                st, res = "valid_scored", False
            elif iid in errors:
                st, res, detail = "eval_error", None, "evaluator_error"
                if eval_log and f"{iid}: Test timed out" in read(eval_log[0]):
                    detail = "evaluator_test_timeout_1800s"
            elif iid in empty:
                st, res = "empty_patch", False
            else:
                st, res = "unknown", None
                warn(f"{run}/{iid}: in no report list")
            if (iid in empty) != (patch is None):
                warn(f"{run}/{iid}: empty_patch_ids disagrees with preds.json")
            rows.append(row(ds, run, harness, iid, patch, res, st, rel_rep, rel_preds, detail))
        # report-level sanity
        for k, n in [("resolved_instances", len(resolved)), ("unresolved_instances", len(unresolved)),
                     ("error_instances", len(errors)), ("empty_patch_instances", len(empty))]:
            if rep[k] != n:
                warn(f"{run}: {k}={rep[k]} but id list has {n}")
    return rows


def agent_rows(cache, ds, harness, warn):
    root = os.path.join(cache, ds)
    jl = glob.glob(os.path.join(root, "results", "*.jsonl"))
    assert len(jl) == 1, (ds, jl)
    jl = jl[0]
    run = os.path.basename(jl)[: -len(".jsonl")]
    rel_jl = os.path.relpath(jl, root)
    recs = [json.loads(x) for x in open(jl) if x.strip()]
    seen = set()
    rows = []
    for r in recs:
        iid = r["task_metadata"]["instance_id"]
        if iid in seen:
            warn(f"{run}/{iid}: duplicate JSONL row")
        seen.add(iid)
        pred = norm_patch(r.get("predicted"))
        ss = r.get("score_status")
        base = os.path.join("results", run, "artifacts", f"swe_{iid}", "workspace", "swebench_eval", iid)
        pd_rel, rp_rel, lg_rel = (f"{base}/{n}" for n in ("patch.diff", "report.json", "run_instance.log"))
        pd_abs, rp_abs, lg_abs = (os.path.join(root, p) for p in (pd_rel, rp_rel, lg_rel))
        patch, psrc = pred, rel_jl
        if os.path.exists(pd_abs):
            pdv = norm_patch(read(pd_abs))
            if pdv != pred:
                warn(f"{run}/{iid}: patch.diff != JSONL predicted")
            patch, psrc = pdv, pd_rel
        # task JSON consistency
        tj = os.path.join(root, "results", run, "tasks", f"swe_{iid}.json")
        if os.path.exists(tj):
            t = json.load(open(tj))[0]
            if norm_patch(t.get("predicted")) != pred or t.get("correct") != r.get("correct"):
                warn(f"{run}/{iid}: task JSON != JSONL")
        detail = None
        if ss != "valid_scored":
            st, res, lsrc = ss, None, rel_jl
            # a patch may exist but was never evaluated (e.g. image build failure); kept, not usable
        elif not patch:
            st, res, lsrc = "empty_patch", r.get("correct"), rel_jl
        elif os.path.exists(rp_abs):
            rep = json.load(open(rp_abs))
            res = (rep[iid] if iid in rep else rep)["resolved"]
            st, lsrc = "valid_scored", rp_rel
            if res != r.get("correct"):
                warn(f"{run}/{iid}: report.json resolved={res} != JSONL correct={r.get('correct')}")
        else:
            st, res, lsrc = "eval_error", None, lg_rel if os.path.exists(lg_abs) else rel_jl
            detail = "no_report_json"
            if os.path.exists(lg_abs) and "Failed to apply patch to container" in read(lg_abs):
                detail = "patch_apply_failed"
            if r.get("correct") is True:
                warn(f"{run}/{iid}: JSONL correct=True but no report.json")
        rows.append(row(ds, run, harness, iid, patch, res, st, lsrc, psrc, detail))
    return rows


def summarize(rows):
    by = defaultdict(list)
    for r in rows:
        by[(r["dataset"], r["run"], r["harness"])].append(r)
    out = []
    for (ds, run, h), rs in by.items():
        out.append({
            "dataset": ds, "run": run, "harness": h,
            "tasks": len(rs),
            "usable": sum(r["usable"] for r in rs),
            "resolved_usable": sum(r["usable"] and r["resolved"] for r in rs),
            "status_counts": dict(Counter(r["status"] + (":" + r["status_detail"] if r["status_detail"] else "") for r in rs)),
        })
    return out


def cross_run(rows, exclude_runs=()):
    """Per instance: unique usable patches (exact-duplicate dropped), pass/fail split."""
    per = defaultdict(dict)  # iid -> sha -> set(resolved)
    attempts = Counter()
    for r in rows:
        if not r["usable"] or r["run"] in exclude_runs:
            continue
        attempts[r["instance_id"]] += 1
        h = hashlib.sha256(r["patch"].encode()).hexdigest()
        per[r["instance_id"]].setdefault(h, set()).add(r["resolved"])
    both, conflict = [], []
    for iid, d in per.items():
        labels = [x for s in d.values() for x in s]
        if any(len(s) > 1 for s in d.values()):
            conflict.append(iid)  # same patch labelled both ways
        if True in labels and False in labels:
            both.append(iid)
    dist = Counter(attempts[i] for i in attempts)
    uniq = Counter(len(per[i]) for i in per)
    return {
        "excluded_runs": list(exclude_runs),
        "instances_with_usable_attempt": len(per),
        "instances_with_pass_and_fail": len(both),
        "pass_and_fail_ids": sorted(both),
        "identical_patch_labelled_both_ways": conflict,
        "usable_attempts_per_instance": {str(k): v for k, v in sorted(dist.items())},
        "unique_usable_patches_per_instance": {str(k): v for k, v in sorted(uniq.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "data", "public", "gemma4-own-attempts"))
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    shas = {}
    if not a.no_download:
        download(a.cache, shas)
    else:
        try:
            from huggingface_hub import HfApi
            shas = {ds: HfApi().dataset_info(f"{USER}/{ds}").sha for ds, _ in DATASETS}
        except Exception as e:  # offline
            print("could not fetch shas:", e, file=sys.stderr)
    warnings = []
    warn = lambda m: (warnings.append(m), print("WARN", m, file=sys.stderr))
    rows = []
    for ds, harness in DATASETS:
        fn = sweagent_rows if ds == SWEAGENT_ID else agent_rows
        rows += fn(a.cache, ds, harness, warn)
    rows.sort(key=lambda r: (r["dataset"], r["run"], r["instance_id"]))
    with open(os.path.join(a.out, "attempts.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    smoke = [r["run"] for r in rows if r["run"].endswith("podman-smoke")]
    summary = {
        "dataset_shas": shas,
        "runs": summarize(rows),
        "cross_run_all": cross_run(rows),
        "cross_run_excluding_smoke": cross_run(rows, exclude_runs=set(smoke)),
        "warnings": warnings,
    }
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "dataset_shas"}, indent=1))


if __name__ == "__main__":
    main()
