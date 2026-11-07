#!/usr/bin/env python3
"""Log the progress of tonight's lab runs to W&B from the Mac (specs nonpython-rubber-stamp and lite-repair-replication).
Every 15 minutes it reads counts through the lab login script and logs them; it ends when the GPU queue prints QUEUE_DONE."""
import json, os, subprocess, time

import wandb

SSH = os.path.expanduser("~/Documents/asankhya/ssh.sh")
REMOTE = r"""echo MARK
E=<workdir>/swe-env; ML=<workdir>/gemma4-paper-track/ml
c() { [ -f "$1" ] && wc -l < "$1" || echo 0; }
g() { grep -c "$1" "$2" 2>/dev/null || true; }
<workdir>/swe-env/venv20/bin/python - <<P
import json, os
p = "$ML/runs/nonpython/preds.json"
d = json.load(open(p)) if os.path.exists(p) else {}
q = "$ML/runs/nonpython-thinking/preds.json"
t = json.load(open(q)) if os.path.exists(q) else {}
print(json.dumps(dict(
  arm_issues_done=len(t), arm_nonempty=sum(bool(v.get("model_patch")) for v in t.values()),
  arm_graded=int("$(c $ML/runs/nonpython-thinking/labels.jsonl)"),
  np_issues_done=len(d), np_nonempty=sum(bool(v.get("model_patch")) for v in d.values()),
  np_graded=int("$(c $ML/runs/nonpython/labels.jsonl)"), np_all_done=int("$(g ALL_DONE $ML/logs/np_full.log)" or 0),
  pull_nonpython=int("$(g ' OK ' $ML/logs/ml_pull.log)" or 0), pull_lite=int("$(g ' OK ' $ML/logs/lite_pull.log)" or 0),
  gate_lines=int("$(c $E/existing-test-gate-lite/full/runs.jsonl)"),
  repair_tests=int("$(c $E/test-repair/lite/tests/preds.jsonl)"), repair_review=int("$(c $E/test-repair/lite/review/preds.jsonl)"),
  lite_all_done=int("$(g ALL_DONE $E/existing-test-gate-lite/chain.log)" or 0),
  seed1_tests=int("$(c $E/test-repair/seed1/tests/preds.jsonl)"), seed1_review=int("$(c $E/test-repair/seed1/review/preds.jsonl)"),
  seed2_tests=int("$(c $E/test-repair/seed2/tests/preds.jsonl)"), seed2_review=int("$(c $E/test-repair/seed2/review/preds.jsonl)"),
  queue_done=int("$(g QUEUE_DONE $ML/logs/np_queue.log)" or 0),
  gpu_mib=int("$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"),
  gpu_pct=int("$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -1)"))))
P
"""


def read():
    t = subprocess.run(["perl", "-e", "alarm 90; exec @ARGV", "bash", SSH, REMOTE], capture_output=True, text=True).stdout
    lines = t.split("MARK", 1)[-1].strip().splitlines()
    return json.loads(lines[-1]) if lines else None


run = wandb.init(project="gemma4-paper-track", group="nonpython-and-lite-repair", name="lab-progress-2026-11-06", id="124035fn", resume="allow",
                 config=dict(model="google/gemma-4-31B-it-qat-w4a16-ct", revision="52f3f65b", temperature=0, seed="none: one run per issue",
                             specs=["spec/nonpython-rubber-stamp.md", "spec/lite-repair-replication.md"], git_commit="efd2b38"))
while True:
    try:
        r = read()
    except Exception as e:
        print("read failed", e, flush=True); r = None
    if r:
        print(r, flush=True); run.log(r)
        if r["queue_done"]:
            break
    time.sleep(900)
run.finish()
