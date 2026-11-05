#!/bin/bash
# Spec addendum 3 (spec/judge-as-actor.md): complete the gpt-oss-20b comparison on the 133 stamped own patches with one
# vLLM server: (1) gpt-oss reading locally, (2) forced final answer for the 33 step-limit runs, (3) rerun of the 8
# errored runs with the timeout message truncated. Log ends with ALL_DONE or SERVER_FAILED.
#   bash judge_actor_gptoss_complete.sh > $E/logs/judge_gptoss_complete.log 2>&1
set -uo pipefail
B=<workdir>/gemma4-paper-track
E=<workdir>/swe-env
J=$E/judge-as-actor
JOBS=$J/jobs.jsonl
mkdir -p $J/gptoss-reader $J/gptoss-final $J/gptoss-rerun $E/work $E/tmp
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=$B/hf HF_HUB_OFFLINE=1 TMPDIR=$E/tmp
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
export VLLM_BASE=http://127.0.0.1:18000/v1
export SERVED_MODEL=gpt-oss-20b MODEL_ID=openai/gpt-oss-20b MODEL_REVISION=6cee5e81ee83917806bbde320786a8fb61efebee
export TOOL_MODE=bash MAX_TOKENS=32768
Q=<workdir>/hf-cache/hub/models--openai--gpt-oss-20b/snapshots/$MODEL_REVISION
$B/.venv-vllm/bin/vllm serve $Q --served-model-name gpt-oss-20b --host 127.0.0.1 --port 18000 --max-model-len 131072 \
  --gpu-memory-utilization ${GPU_UTIL:-0.78} --max-num-seqs 16 --enable-prefix-caching \
  --enable-auto-tool-choice --tool-call-parser openai > $J/gptoss-rerun/vllm.log 2>&1 &
VP=$!
echo "start $(date -u +%FT%TZ)"
for i in $(seq 1 180); do curl -sf 127.0.0.1:18000/health >/dev/null && break; kill -0 $VP 2>/dev/null || break; sleep 10; done
curl -sf 127.0.0.1:18000/health >/dev/null || { echo SERVER_FAILED; tail -30 $J/gptoss-rerun/vllm.log; exit 1; }
echo "server up $(date -u +%FT%TZ)"

echo "reader $(date -u +%FT%TZ)"
R=(--base $VLLM_BASE --model gpt-oss-20b --tag gpt-oss-20b-local --prompts $J/reader_p1_133.jsonl
   --out $J/gptoss-reader/fresh_gpt-oss-20b-local.jsonl --workers 16)
python3 $B/probe/local_judging.py run "${R[@]}" --max-tokens 3000
python3 $B/probe/local_judging.py run "${R[@]}" --max-tokens 16000 --redo-unparsed
echo "reader rows $(wc -l < $J/gptoss-reader/fresh_gpt-oss-20b-local.jsonl) $(date -u +%FT%TZ)"

echo "finalize $(date -u +%FT%TZ)"
$E/venv-mswea170/bin/python $E/scripts/judge_actor.py finalize --jobs $JOBS --src $J/gptoss --out $J/gptoss-final --workers 6
echo "finalize rows $(wc -l < $J/gptoss-final/runs.jsonl) $(date -u +%FT%TZ)"

echo "rerun $(date -u +%FT%TZ)"
IDS=django__django-11551,django__django-11603,django__django-12741,django__django-14140,django__django-15104,django__django-16333,pylint-dev__pylint-7080,sympy__sympy-15809
$E/venv-mswea170/bin/python $E/scripts/judge_actor.py run --jobs $JOBS --sets pilot --ids $IDS --out $J/gptoss-rerun --workers 6
RC=$?
kill $VP 2>/dev/null; sleep 20; pkill -f "served-model-name gpt-oss-20b" 2>/dev/null
echo "ALL_DONE rc=$RC rerun_rows=$(wc -l < $J/gptoss-rerun/runs.jsonl 2>/dev/null) $(date -u +%FT%TZ)"
