#!/bin/bash
# Patches tested with their fix removed (spec/existing-test-gate.md, addendum 2). CPU only, one step at a time so that at
# most 4 sandboxes run. Grader check on 30 control patches, gate on the 68 affected patches, then a local grade of those
# patches. $D/jobs.jsonl must exist. Resumes: the gate and the grader skip what is finished.
#   nohup setsid bash scripts/lab/applyfix_chain.sh </dev/null >/dev/null 2>&1 &
set -uo pipefail
E=<workdir>/swe-env
D=$E/existing-test-gate-applyfix
export HF_HOME=$E/hf HF_DATASETS_OFFLINE=1 TMPDIR=$E/tmp
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
export CUDA_VISIBLE_DEVICES=
PY=$E/venv-mswea170/bin/python
exec >> "$D/chain.log" 2>&1

echo "start $(date -u +%FT%TZ)"
cd $E/scripts
HF_HUB_OFFLINE=1 $PY eval_apptainer.py validate --entry 20250807_mini-v1.7.0_gpt-oss-120b --n 30 --out "$D/validate.jsonl" --workers 4
echo "grader check done $(date -u +%FT%TZ)"

export HF_HUB_OFFLINE=1
GATE_DIR=$D OUT=full WORKERS=4 bash $E/scripts/lab/existing_test_gate.sh
echo "gate done $(date -u +%FT%TZ)"

mkdir -p "$D/start-grade"
$PY - "$D" <<'PY'
import collections, json, os, re, sys
d = sys.argv[1]
by = collections.defaultdict(list)
for l in open(os.path.join(d, "jobs.jsonl")):
    j = json.loads(l)
    for p in j["patches"]:
        by[p["writer"]].append(dict(instance_id=j["instance_id"], model_patch=p["patch"]))
for w, rows in by.items():
    with open(os.path.join(d, "start-grade", "preds." + re.sub(r"[^\w.-]", "_", w) + ".jsonl"), "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
PY
for p in "$D"/start-grade/preds.*.jsonl; do
    w=$(basename "$p" .jsonl); w=${w#preds.}
    $PY eval_apptainer.py eval --preds "$p" --out "$D/start-grade/labels.$w.jsonl" --workers 4 --retry-ungraded
done
echo "ALL_DONE $(date -u +%FT%TZ)"
