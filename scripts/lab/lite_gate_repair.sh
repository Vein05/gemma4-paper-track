#!/bin/bash
# Gate, repair and start-patch grades on Lite patches (spec/lite-repair-replication.md), from $E/scripts/lab on the server.
# 1. Wait for the Lite image pull. 2. Gate on the CPUs. 3. Grade blocked start and reference patches on the CPUs.
# 4. When the GPU queue creates $E/test-repair/lite_gpu_go and the GPU is idle, run the repair chain. Every step resumes.
E=<workdir>/swe-env
ML=<workdir>/gemma4-paper-track/ml
G=$E/existing-test-gate-lite
R=$E/test-repair/lite
export SWE_DATASET=princeton-nlp/SWE-bench_Lite HF_HOME=$E/hf HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TMPDIR=$E/tmp
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export SANDBOX_MEM_KB=64000000  # memory cap and cleanup for agent commands (run_gemma_mini.py, 2026-11-08)
nohup setsid bash <workdir>/swe-env/scripts/lab/memory_watchdog.sh </dev/null >/dev/null 2>&1 &  # a second copy exits at once
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
PY=$E/venv-mswea170/bin/python
exec >> $G/chain.log 2>&1
echo "wait for pull $(date -u +%FT%TZ)"
until grep -q ALL_DONE $ML/logs/lite_pull.log 2>/dev/null; do sleep 120; done
echo "gate start $(date -u +%FT%TZ)"
GATE_DIR=$G OUT=full WORKERS=${GATE_WORKERS:-24} bash $E/scripts/lab/existing_test_gate.sh
echo "gate end $(date -u +%FT%TZ)"
mkdir -p $R/start $R/reference
$PY $E/scripts/lite_repair.py grade_files --gate $G/full --gate-jobs $G/jobs.jsonl --out $R
for k in start reference; do
  $PY $E/scripts/eval_apptainer.py eval --preds $R/$k/preds_grade.jsonl --out $R/$k/labels.jsonl --workers 8 --dataset $SWE_DATASET
done
echo "start and reference grades end $(date -u +%FT%TZ)"
until [ -f "$E/test-repair/lite_gpu_go" ] && \
  [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)" -lt 2000 ]; do sleep 120; done
echo "repair start $(date -u +%FT%TZ)"
OUT=lite GATE=$G/full GATE_JOBS=$G/jobs.jsonl GPU_UTIL=${GPU_UTIL:-0.70} WORKERS=${WORKERS:-8} bash $E/scripts/lab/test_repair_chain.sh
echo "ALL_DONE $(date -u +%FT%TZ)"
