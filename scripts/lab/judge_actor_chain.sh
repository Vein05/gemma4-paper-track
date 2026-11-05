#!/bin/bash
# Judge as actor on the lab A100 (spec/judge-as-actor.md). Serves the judge with vLLM, waits for it, runs
# scripts/judge_actor.py run on the given sets, stops the server. Log ends with ALL_DONE or SERVER_FAILED.
#
#   JUDGE=gemma SETS=pilot bash judge_actor_chain.sh                 # pilot: Gemma on its 133 stamped own patches
#   JUDGE=gemma SETS=own,others-fail bash judge_actor_chain.sh       # full core set (resumes; pilot rows are kept)
#   JUDGE=qwen  SETS=pilot bash judge_actor_chain.sh
#   JUDGE=gptoss SETS=pilot bash judge_actor_chain.sh               # spec addendum 1
#   JUDGE=gemma SETS=pilot IDS=django__django-11099,sympy__sympy-13091 STEPS=15 bash judge_actor_chain.sh   # smoke
set -uo pipefail
B=<workdir>/gemma4-paper-track
E=<workdir>/swe-env
OUT=$E/judge-as-actor/${JUDGE:?JUDGE}
JOBS=$E/judge-as-actor/jobs.jsonl
mkdir -p "$OUT" $E/work $E/tmp
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=$B/hf HF_HUB_OFFLINE=1 TMPDIR=$E/tmp
# sandboxes: the lab's unprivileged Apptainer, images pulled once into swe-env/sif (pull_images.sh)
export APPTAINER=$E/apptainer/bin/apptainer SIF_DIR=$E/sif WORK=$E/work
export APPTAINER_CACHEDIR=$E/cache APPTAINER_TMPDIR=$E/tmp APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"
export VLLM_BASE=http://127.0.0.1:18000/v1
V=$B/.venv-vllm/bin/vllm
case "$JUDGE" in
  gemma)
    export SERVED_MODEL=gemma4-qat MODEL_ID=google/gemma-4-31B-it-qat-w4a16-ct MODEL_REVISION=52f3f65bc7a02d555763bc923bd1d9094898219d
    # the writer runs' settings: 131,072 context, thinking off, temperature 0 (model_kwargs in judge_actor.yaml)
    $V serve $B/models/gemma-4-31B-it-qat-w4a16-ct --served-model-name gemma4-qat --host 127.0.0.1 --port 18000 \
      --max-model-len 131072 --gpu-memory-utilization ${GPU_UTIL:-0.90} --max-num-seqs 16 --enable-prefix-caching \
      --reasoning-parser gemma4 --limit-mm-per-prompt '{"image": 0, "audio": 0}' > "$OUT/vllm.log" 2>&1 &
    ;;
  qwen)
    export SERVED_MODEL=qwen3-32b MODEL_ID=Qwen/Qwen3-32B MODEL_REVISION=9216db5781bf21249d130ec9da846c4624c16137
    Q=<workdir>/hf-cache/hub/models--Qwen--Qwen3-32B/snapshots/9216db5781bf21249d130ec9da846c4624c16137
    # as in the check run (open_panel_chain.sh): bf16, 32,768 context; thinking off through chat_template_kwargs
    $V serve $Q --served-model-name qwen3-32b --host 127.0.0.1 --port 18000 --max-model-len 32768 \
      --gpu-memory-utilization ${GPU_UTIL:-0.95} --max-num-seqs 16 --enable-prefix-caching \
      --default-chat-template-kwargs '{"enable_thinking": false}' > "$OUT/vllm.log" 2>&1 &
    ;;
  gptoss)
    export SERVED_MODEL=gpt-oss-20b MODEL_ID=openai/gpt-oss-20b MODEL_REVISION=6cee5e81ee83917806bbde320786a8fb61efebee
    Q=<workdir>/hf-cache/hub/models--openai--gpt-oss-20b/snapshots/6cee5e81ee83917806bbde320786a8fb61efebee
    # spec addendum 1: MXFP4 as shipped, 131,072 context, default reasoning effort (medium), temperature 0
    $V serve $Q --served-model-name gpt-oss-20b --host 127.0.0.1 --port 18000 --max-model-len 131072 \
      --gpu-memory-utilization ${GPU_UTIL:-0.78} --max-num-seqs 16 --enable-prefix-caching \
      --enable-auto-tool-choice --tool-call-parser openai > "$OUT/vllm.log" 2>&1 &
    export TOOL_MODE=bash  # one declared bash tool; judge_actor.py turns the call into the text command
    ;;
  *) echo "JUDGE must be gemma, qwen or gptoss"; exit 1;;
esac
VP=$!
echo "start $JUDGE sets=${SETS:-pilot} $(date -u +%FT%TZ)"
for i in $(seq 1 180); do curl -sf 127.0.0.1:18000/health >/dev/null && break; kill -0 $VP 2>/dev/null || break; sleep 10; done
curl -sf 127.0.0.1:18000/health >/dev/null || { echo SERVER_FAILED; tail -30 "$OUT/vllm.log"; exit 1; }
echo "server up $(date -u +%FT%TZ)"
ARGS=(--jobs "$JOBS" --sets "${SETS:-pilot}" --out "$OUT" --workers "${WORKERS:-6}")
[ -n "${IDS:-}" ] && ARGS+=(--ids "$IDS")
[ -n "${STEPS:-}" ] && ARGS+=(--step-limit "$STEPS")
$E/venv-mswea170/bin/python $E/scripts/judge_actor.py run "${ARGS[@]}"
RC=$?
kill $VP 2>/dev/null; sleep 20; pkill -f "served-model-name $SERVED_MODEL" 2>/dev/null
echo "ALL_DONE rc=$RC rows=$(wc -l < "$OUT/runs.jsonl" 2>/dev/null) $(date -u +%FT%TZ)"
