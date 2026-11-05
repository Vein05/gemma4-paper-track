#!/bin/bash
# LiveCodeBench model sweep on the lab A100 (spec/lcb-model-sweep.md). For each model: start vLLM, pilot 5 programs,
# write programs for the 292 judged problems, grade them on CPU in the background, judge its own programs plus the 839
# existing ones, stop vLLM. Then Qwen3-32B judges every new program. Every step resumes.
#   nohup bash lcb_sweep_chain.sh > sweep/chain.log 2>&1 &     (from <workdir>/gemma4-paper-track/lcb)
# Log lines to look for: MODEL_START, PILOT_FAIL, SERVER_FAILED, MODEL_DONE, ALL_DONE.
L=<workdir>/gemma4-paper-track/lcb
B=<workdir>/gemma4-paper-track
H=<workdir>/hf-cache/hub
C=<workdir>/completed-but-wrong-pilot/hf/hub
A=<workdir>/swe-env/apptainer/bin/apptainer
S=$L/sweep
V=$B/.venv-vllm/bin/vllm
PORT=18020
cd $L || exit 1
mkdir -p $S $L/work/tmp
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
snap() { ls -d $1/snapshots/* | head -1; }
box() { $A exec --contain --cleanenv --env HF_HOME=/lcb/hf --env PYTHONNOUSERSITE=1 -B $L:/lcb -B $L/work/tmp:/tmp \
          --pwd /lcb/LiveCodeBench $L/python311.sif "$@"; }
EVAL="/lcb/venv/bin/python -m lcb_runner.runner.custom_evaluator --scenario codegeneration --release_version release_v6
  --num_process_evaluate 16 --timeout 6"
GEMMA='--reasoning-parser gemma4 --limit-mm-per-prompt {"image":0,"audio":0}'

wait_server() {
  for i in $(seq 1 120); do curl -s 127.0.0.1:$PORT/v1/models >/dev/null && return 0
    kill -0 $VP 2>/dev/null || return 1; sleep 10; done; return 1; }
stop_server() { kill $VP 2>/dev/null; sleep 20; pkill -f "port $PORT" ; sleep 10; }

one() {  # name path extra_body vllm_flags...
  local N=$1 P=$2 X=$3; shift 3
  echo "MODEL_START $N $(date -u)"
  if [ -f $S/$N.judged ]; then echo "already judged $N"; return; fi
  $V serve $P --served-model-name $N --port $PORT --host 127.0.0.1 --max-model-len 16384 "$@" > $S/vllm_$N.log 2>&1 &
  VP=$!
  if ! wait_server; then echo "SERVER_FAILED $N"; tail -5 $S/vllm_$N.log; stop_server; return; fi
  box /lcb/venv/bin/python /lcb/scripts/lcb_generate.py --url http://127.0.0.1:$PORT/v1/chat/completions --model $N \
      --extra "$X" --ids /lcb/sweep/sweep_ids.json --out /lcb/sweep/$N.jsonl --max-tokens 8000 --workers 16 --timeout 7200 --limit 5
  ok=$(python3 -c "import json;print(sum(bool((json.loads(l).get('code') or '').strip()) for l in open('$S/$N.jsonl')))")
  if [ "$ok" -lt 3 ]; then echo "PILOT_FAIL $N ($ok of 5 with code)"; stop_server; return; fi
  box /lcb/venv/bin/python /lcb/scripts/lcb_generate.py --url http://127.0.0.1:$PORT/v1/chat/completions --model $N \
      --extra "$X" --ids /lcb/sweep/sweep_ids.json --out /lcb/sweep/$N.jsonl --max-tokens 8000 --workers 16 --timeout 7200
  box /lcb/venv/bin/python /lcb/scripts/lcb_generate.py --url http://127.0.0.1:$PORT/v1/chat/completions --model $N \
      --extra "$X" --ids /lcb/sweep/sweep_ids.json --out /lcb/sweep/$N.jsonl --max-tokens 8000 --workers 16 --timeout 7200
  echo "generated $N $(wc -l < $S/$N.jsonl) $(date -u)"
  ( box /lcb/venv/bin/python /lcb/scripts/lcb_generate.py --out /lcb/sweep/$N.jsonl --export /lcb/sweep/$N.json --fill-empty \
      && box $EVAL --custom_output_file /lcb/sweep/$N.json ) > $S/grade_$N.log 2>&1 &
  python3 $S/lcb_sweep_prompts.py --existing $S/lcb_p1.jsonl --gen $S/$N.jsonl --writer $N --out $S/${N}_p1.jsonl
  cat $S/${N}_p1.jsonl $S/lcb_p1.jsonl > $S/judge_$N.jsonl
  LOCAL_JUDGE_EXTRA="$X" python3 $S/local_judging.py run --base http://127.0.0.1:$PORT/v1 --model $N --tag $N \
      --prompts $S/judge_$N.jsonl --out $S/scores_$N.jsonl --workers 16 --max-tokens 3000
  LOCAL_JUDGE_EXTRA="$X" python3 $S/local_judging.py run --base http://127.0.0.1:$PORT/v1 --model $N --tag $N \
      --prompts $S/judge_$N.jsonl --out $S/scores_$N.jsonl --workers 16 --max-tokens 8000 --redo-unparsed
  touch $S/$N.judged
  stop_server
  echo "MODEL_DONE $N rows $(wc -l < $S/scores_$N.jsonl) $(date -u)"
}

echo "start $(date -u)"
NOX='{}'; GOFF='{"chat_template_kwargs":{"enable_thinking":false}}'
VLLM_DISABLED_KERNELS= one gemma-4-12b $B/models/gemma-4-12B-it-qat-w4a16-ct "$GOFF" --gpu-memory-utilization 0.90 $GEMMA
VLLM_DISABLED_KERNELS=CutlassFP8ScaledMMLinearKernel one gemma-4-26b-a4b $B/models/gemma-4-26B-A4B-it "$GOFF" \
  --gpu-memory-utilization 0.90 --quantization fp8 --enforce-eager $GEMMA
one gpt-oss-20b $(snap $H/models--openai--gpt-oss-20b) '{"reasoning_effort":"low"}' --gpu-memory-utilization 0.90
one olmo-3.1-32b $B/models/olmo-3.1-32B-Instruct "$NOX" --gpu-memory-utilization 0.92
one glm-4-9b $(snap $C/models--zai-org--glm-4-9b-chat-hf) "$NOX" --gpu-memory-utilization 0.90
one phi-4-mini $(snap $C/models--microsoft--Phi-4-mini-instruct) "$NOX" --gpu-memory-utilization 0.90
one mistral-small-3.2-24b $(snap $H/models--mistralai--Mistral-Small-3.2-24B-Instruct-2506) "$NOX" \
  --gpu-memory-utilization 0.92 --tokenizer-mode mistral --config-format mistral --load-format mistral
one nemotron-nano-9b-v2 $(snap $H/models--nvidia--NVIDIA-Nemotron-Nano-9B-v2) "$NOX" --gpu-memory-utilization 0.90 \
  --trust-remote-code --mamba-ssm-cache-dtype float32
one seed-oss-36b $(snap $H/models--ByteDance-Seed--Seed-OSS-36B-Instruct) '{"chat_template_kwargs":{"thinking_budget":0}}' \
  --gpu-memory-utilization 0.95 --max-num-seqs 8

echo "QWEN_START $(date -u)"
cat $S/*_p1.jsonl | grep -v '"writer": "gemma-4-31b"\|"writer": "claude-3.5-sonnet"\|"writer": "deepseek-v3"' > $S/qwen_new_prompts.jsonl
Q=$(snap $H/models--Qwen--Qwen3-32B)
$V serve $Q --served-model-name qwen3-32b --port $PORT --host 127.0.0.1 --max-model-len 32768 --gpu-memory-utilization 0.95 \
  > $S/vllm_qwen.log 2>&1 &
VP=$!
if wait_server; then
  LOCAL_JUDGE_NO_THINK=1 python3 $S/local_judging.py run --base http://127.0.0.1:$PORT/v1 --model qwen3-32b --tag qwen3-32b-local \
      --prompts $S/qwen_new_prompts.jsonl --out $S/scores_qwen3-32b-local.jsonl --workers 16 --max-tokens 3000
  LOCAL_JUDGE_NO_THINK=1 python3 $S/local_judging.py run --base http://127.0.0.1:$PORT/v1 --model qwen3-32b --tag qwen3-32b-local \
      --prompts $S/qwen_new_prompts.jsonl --out $S/scores_qwen3-32b-local.jsonl --workers 16 --max-tokens 8000 --redo-unparsed
else echo "SERVER_FAILED qwen3-32b"; fi
stop_server
wait
echo "ALL_DONE $(date -u)"
