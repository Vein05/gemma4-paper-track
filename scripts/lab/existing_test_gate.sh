#!/bin/bash
# Existing-test gate on the lab server, CPU only (spec/existing-test-gate.md). Resumes: finished issues are skipped.
#
#   IDS=a,b,c WORKERS=3 OUT=smoke bash existing_test_gate.sh     # smoke test on named issues
#   OUT=full WORKERS=24 bash existing_test_gate.sh                 # all issues in jobs.jsonl
set -uo pipefail
E=<workdir>/swe-env
B=<workdir>/gemma4-paper-track
D=$E/existing-test-gate
mkdir -p $D/${OUT:?OUT} $E/work $E/tmp
export HF_HOME=$E/hf HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TMPDIR=$E/tmp
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
CUDA_VISIBLE_DEVICES= $E/venv-mswea170/bin/python $E/scripts/existing_test_gate.py run --jobs $D/jobs.jsonl \
  --out $D/$OUT/runs.jsonl --workers ${WORKERS:-24} ${IDS:+--ids $IDS} > $D/$OUT/run.log 2>&1
echo ALL_DONE >> $D/$OUT/run.log
