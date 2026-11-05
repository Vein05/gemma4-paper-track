#!/usr/bin/env python3
"""LiveCodeBench model sweep: does each open model rubber-stamp its own programs? (spec/lcb-model-sweep.md; written
before any sweep result was read).

Inputs in data/lab-runs/lcb-sweep/ (copied from the lab's lcb/sweep/): <model>.jsonl (programs),
<model>_codegeneration_output_eval_all.json (grades), <model>_p1.jsonl (prompts of the new programs), scores_<model>.jsonl
(the model's scores of its own and the 839 existing programs), scores_qwen3-32b-local.jsonl (Qwen3-32B on the new
programs). Existing programs: data/livecodebench-pilot/judging/programs.jsonl and Qwen3-32B's scores
scripts/derived/lcb_qwen3-32b-local.jsonl.

Usage (from scripts/): python3 lcb_sweep_analysis.py > derived/lcb_sweep_2026-11-04.json
"""
import json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from open_panel_check import leniency_boot, flagged  # noqa: E402

ROOT = os.path.join(HERE, "..")
D = os.path.join(ROOT, "data", "lab-runs", "lcb-sweep")
PROGRAMS = os.path.join(ROOT, "data", "livecodebench-pilot", "judging", "programs.jsonl")
QWEN_OLD = os.path.join(HERE, "derived", "lcb_qwen3-32b-local.jsonl")
MODELS = ["gemma-4-12b", "gemma-4-26b-a4b", "gpt-oss-20b", "olmo-3.1-32b", "glm-4-9b", "phi-4-mini",
          "nemotron-nano-9b-v2", "seed-oss-36b"]
GEMMA_FAMILY = {"gemma-4-12b", "gemma-4-26b-a4b", "gemma-4-31b"}
OLD_WRITERS = ["gemma-4-31b", "claude-3.5-sonnet", "deepseek-v3"]


def scores(path):
    """pid -> score; the last parsed answer wins (the 8,000-token re-ask comes after the first pass)."""
    out = {}
    for r in map(json.loads, open(path)):
        if r.get("err") is None and r.get("parsed") is not None:
            out[r["pid"]] = r["parsed"]
    return out


def main():
    old = {r["pid"]: r for r in map(json.loads, open(PROGRAMS))}
    q = scores(QWEN_OLD)
    qn = os.path.join(D, "scores_qwen3-32b-local.jsonl")
    if os.path.exists(qn):
        q.update(scores(qn))
    ids = set(json.load(open(os.path.join(ROOT, "data", "livecodebench-pilot", "judging", "sweep_ids.json"))))
    res = {}
    for m in MODELS:
        need = [os.path.join(D, f) for f in (f"{m}_p1.jsonl", f"scores_{m}.jsonl", f"{m}_codegeneration_output_eval_all.json")]
        if not all(os.path.exists(f) for f in need):
            res[m] = "not run (server or pilot failed, or files missing)"; continue
        grade = {e["question_id"]: int(bool(e["graded_list"][0])) for e in json.load(open(need[2])) if e["question_id"] in ids}
        new = {r["pid"]: dict(iid=r["iid"], writer=m, y=grade[r["iid"]]) for r in map(json.loads, open(need[0]))}
        s = scores(need[1])
        rows = [(p, x) for p, x in new.items()]
        rows += [(p, dict(iid=x["iid"], writer=x["writer"], y=x["y"])) for p, x in old.items()
                 if not (m in GEMMA_FAMILY and x["writer"] in GEMMA_FAMILY)]
        rows = [(p, x) for p, x in rows if p in s and p in q]
        y = np.array([x["y"] for _, x in rows]); wr = np.array([x["writer"] for _, x in rows])
        iss = np.array([x["iid"] for _, x in rows])
        S = np.array([s[p] for p, _ in rows], float); Q = np.array([q[p] for p, _ in rows], float)
        E = S - Q
        own_fail = (wr == m) & (y == 0); oth_fail = (wr != m) & (y == 0)
        r = dict(pass_rate_292=round(sum(grade[i] for i in ids) / len(ids), 3),
                 own_programs_scored=int((wr == m).sum()), own_failing_scored=int(own_fail.sum()),
                 other_writers=sorted(set(wr) - {m}),
                 own_failing_given_100=round(float((S[own_fail] == 100).mean()), 3) if own_fail.any() else None,
                 other_failing_given_100=round(float((S[oth_fail] == 100).mean()), 3) if oth_fail.any() else None,
                 unscored_own=len(new) - int((wr == m).sum()))
        if own_fail.sum() < 30:
            r["leniency_qwen_reference"] = "too few to test"
        else:
            r["leniency_qwen_reference"] = leniency_boot(E, y, wr, iss, m)
        res[m] = r
    # Gemma 4 31B on the same footing (existing scores; other writers Claude 3.5 Sonnet and DeepSeek-V3)
    g = json.load(open(os.path.join(HERE, "derived", "open_panel_check_2026-11-03.json")))["livecodebench"]
    res["gemma-4-31b (existing)"] = dict(leniency_qwen_reference=g["gemma_qwen3-32b_alone"])
    non_gemma = [m for m in MODELS if m not in GEMMA_FAMILY and isinstance(res[m], dict)
                 and isinstance(res[m]["leniency_qwen_reference"], dict)]
    nflag = sum(flagged(res[m]["leniency_qwen_reference"]) for m in non_gemma)
    g31 = g["gemma_qwen3-32b_alone"]["value"]
    above_all = all(g31 > res[m]["leniency_qwen_reference"]["value"] for m in non_gemma)
    out = dict(models=res, non_gemma_tested=len(non_gemma), non_gemma_flagged=nflag)
    out["reading_specific"] = ("Gemma-specific" if nflag <= 1 and above_all else "common" if nflag >= 3 else "mixed")
    fam = [res[m]["leniency_qwen_reference"] for m in ("gemma-4-12b", "gemma-4-26b-a4b")
           if isinstance(res[m], dict) and isinstance(res[m]["leniency_qwen_reference"], dict)]
    if len(fam) == 2:
        k = sum(flagged(f) for f in fam)
        out["reading_family"] = "family trait" if k == 2 else "31B only" if k == 0 else "mixed"
    else:
        out["reading_family"] = "not testable (a Gemma model missing or too few failing programs)"
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
