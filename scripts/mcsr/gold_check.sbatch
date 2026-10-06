#!/bin/bash
#SBATCH -J vein05-gold
#SBATCH -p cpuq
#SBATCH -c 24
#SBATCH --mem 96g
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%j.out
# Reference-patch check on every issue used (spec/fresh-replication.md, addendum 2026-10-06): an issue whose official
# patch does not resolve on Magnolia has an environment problem there, and Gemma's label for it is not used as is.
set -euo pipefail
cd ~/vein05
export HF_HOME=$PWD/hf HF_HUB_OFFLINE=1 TMPDIR=$PWD/tmp WORK=$PWD/work/gold-$SLURM_JOB_ID
export APPTAINER_CACHEDIR=$PWD/apptainer/cache APPTAINER_TMPDIR=$PWD/apptainer/tmp
export APPTAINER_EXEC_FLAGS="" APPTAINER_MOUNT_DIRS=/ddnlus
mkdir -p $TMPDIR $WORK runs/gold
trap 'rm -rf "$WORK"' EXIT
source venv/bin/activate
python - <<'PY'
import json
from datasets import load_dataset
s = json.load(open("data/public/swe-bench-verified-control-fresh/sample.json"))
mini = json.load(open("data/mini50_ids.json"))
ids = s["pilot"] + s["order"][:200] + mini
insts = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")}
with open("runs/gold/preds.jsonl", "w") as f:
    for i in ids:
        f.write(json.dumps(dict(instance_id=i, model_patch=insts[i]["patch"])) + "\n")
print(len(ids), "reference patches")
PY
python scripts/eval_apptainer.py eval --preds runs/gold/preds.jsonl --out runs/gold/labels.jsonl --workers 8
python -c "
import json; r=[json.loads(l) for l in open('runs/gold/labels.jsonl')]
bad=[x['instance_id']+' '+x['status'] for x in r if not x['resolved']]
print('reference patches resolved', len(r)-len(bad), 'of', len(r)); print('\n'.join(bad))"
