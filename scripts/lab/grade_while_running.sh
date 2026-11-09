#!/bin/bash
# Grades finished repair patches while the agents of a test_repair_chain.sh run are still working (2026-11-08). Same
# grader and settings as the chain's grading step; CPU only. Grades already written are skipped, here and by the chain.
# Timeouts are left to the chain's own final pass (RETRY_UNGRADED=1). Stops when the runner has ended.
#   OUT=labelled-repair ARMS="tests labelled" nohup setsid bash grade_while_running.sh </dev/null >/dev/null 2>&1 &
set -uo pipefail
E=<workdir>/swe-env
D=$E/test-repair/${OUT:?OUT}
export HF_HOME=$E/hf HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TMPDIR=$E/tmp
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
PY=$E/venv-mswea170/bin/python
exec >> "$D/grade_while_running.log" 2>&1

running() { pgrep -f "^$PY $E/scripts/test_repair.py run --out $D" > /dev/null; }
calm() { awk -v m="${MAX_LOAD:-64}" '{exit !($1 < m)}' /proc/loadavg; }

echo "start $(date -u +%FT%TZ)"
while running; do
    for arm in ${ARMS:-tests labelled}; do
        for p in "$D/$arm"/preds_grade*.jsonl; do
            [ -f "$p" ] || continue
            running || break 2
            calm || { echo "load high, waiting $(date -u +%FT%TZ)"; break 2; }
            $PY $E/scripts/eval_apptainer.py eval --preds "$p" --out "${p/preds_grade/labels}" \
              --workers "${EVAL_WORKERS:-4}" --dataset "${SWE_DATASET:-princeton-nlp/SWE-bench_Verified}"
        done
    done
    sleep 120
done
echo "runner ended, stopping $(date -u +%FT%TZ)"
