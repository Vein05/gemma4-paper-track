#!/usr/bin/env python3
"""Log an analysis summary (JSON, one entry per model) to W&B, one run per model, with the row files as an artifact.

Usage: python3 log_wandb.py --group selection-test --summary derived/selection_summary_<date>.json \
           --rows derived/selection_*.jsonl [--spec spec/selection-test.md] [--prefix selection]
Project: gemma4-paper-track. Needs WANDB_API_KEY in the environment.
"""
import argparse, hashlib, json, os

import wandb


def flat(d, pre=""):
    out = {}
    for k, v in d.items():
        key = f"{pre}{k}"
        if isinstance(v, dict):
            out.update(flat(v, key + "/"))
        elif isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
            out[key + "/lo"], out[key + "/hi"] = v
        elif isinstance(v, (int, float)):
            out[key] = v
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True); ap.add_argument("--summary", required=True)
    ap.add_argument("--rows", nargs="+", default=[]); ap.add_argument("--spec", default=None)
    ap.add_argument("--prefix", default=None)
    a = ap.parse_args()
    summary = json.load(open(a.summary))
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    for model, res in summary.items():
        tag = model.split("/")[-1]
        run = wandb.init(project="gemma4-paper-track", group=a.group, name=f"{a.prefix or a.group}-{tag}", reinit=True,
                         config=dict(model=model, summary_file=a.summary, summary_sha=sha(a.summary), spec=a.spec,
                                     row_files={os.path.basename(p): sha(p) for p in a.rows}, git_commit="no-git"))
        run.summary.update(flat(res))
        if a.rows:
            art = wandb.Artifact(f"{a.prefix or a.group}-rows", type="dataset")
            for p in a.rows:
                art.add_file(p)
            run.log_artifact(art)
        run.finish()
        print(model, run.id)
