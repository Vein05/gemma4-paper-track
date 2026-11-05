#!/bin/bash
# Repair of the gate's blocked Gemma patches on the lab A100 (spec/test-repair.md): prepare jobs from the gate run,
# serve Gemma 4 31B with vLLM (shared GPU: 0.45 of memory), run both arms, stop the server, grade both arms on CPU.
#   OUT=run1 bash test_repair_chain.sh            (IDS=a,b ARMS=tests OUT=smoke for a smoke test)
set -uo pipefail
E=<workdir>/swe-env
B=<workdir>/gemma4-paper-track
D=$E/test-repair/${OUT:?OUT}
mkdir -p $D $E/work $E/tmp
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=$E/hf HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TMPDIR=$E/tmp
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
export VLLM_BASE=http://127.0.0.1:18000/v1 SERVED_MODEL=gemma4-qat
PY=$E/venv-mswea170/bin/python
exec >> $D/chain.log 2>&1
echo "start $(date -u +%FT%TZ)"
[ -f $D/jobs.jsonl ] || $PY $E/scripts/test_repair.py prepare --gate ${GATE:-$E/existing-test-gate/full} \
  --gate-jobs $E/existing-test-gate/jobs.jsonl --out $D
HF_HOME=$B/hf $B/.venv-vllm/bin/vllm serve $B/models/gemma-4-31B-it-qat-w4a16-ct --served-model-name gemma4-qat \
  --host 127.0.0.1 --port 18000 --max-model-len 65536 --gpu-memory-utilization ${GPU_UTIL:-0.45} --max-num-seqs 8 \
  --enable-prefix-caching --reasoning-parser gemma4 --limit-mm-per-prompt '{"image": 0, "audio": 0}' > $D/vllm.log 2>&1 &
VP=$!
for i in $(seq 1 180); do curl -sf 127.0.0.1:18000/health >/dev/null && break; kill -0 $VP 2>/dev/null || break; sleep 10; done
curl -sf 127.0.0.1:18000/health >/dev/null || { echo "SERVER_FAILED $(date -u +%FT%TZ)"; tail -30 $D/vllm.log; exit 1; }
echo "server up $(date -u +%FT%TZ)"
$PY $E/scripts/test_repair.py run --out $D --workers ${WORKERS:-8} --arms ${ARMS:-tests,review} ${IDS:+--ids $IDS}
kill $VP 2>/dev/null; sleep 20; pkill -f "served-model-name gemma4-qat" 2>/dev/null
echo "server stopped $(date -u +%FT%TZ)"
for arm in $(echo ${ARMS:-tests,review} | tr , ' '); do
  [ -f $D/$arm/preds_grade.jsonl ] && $PY $E/scripts/eval_apptainer.py eval --preds $D/$arm/preds_grade.jsonl \
    --out $D/$arm/labels.jsonl --workers 8
done
echo "ALL_DONE $(date -u +%FT%TZ)"
