#!/bin/bash
# Spec addendum 1 (spec/lcb-model-sweep.md): Nemotron-Nano-9B-v2 with a 16,000-token limit, then Qwen3-32B on its
# programs. Run after lcb_sweep_chain.sh ends (ALL_DONE), from <workdir>/gemma4-paper-track/lcb:
#   nohup bash lcb_sweep_retry.sh > sweep/retry.log 2>&1 &
L=<workdir>/gemma4-paper-track/lcb
B=<workdir>/gemma4-paper-track
H=<workdir>/hf-cache/hub
A=<workdir>/swe-env/apptainer/bin/apptainer
S=$L/sweep
V=$B/.venv-vllm/bin/vllm
PORT=18020
N=nemotron-nano-9b-v2
cd $L || exit 1
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
snap() { ls -d $1/snapshots/* | head -1; }
box() { $A exec --contain --cleanenv --env HF_HOME=/lcb/hf --env PYTHONNOUSERSITE=1 -B $L:/lcb -B $L/work/tmp:/tmp \
          --pwd /lcb/LiveCodeBench $L/python311.sif "$@"; }
EVAL="/lcb/venv/bin/python -m lcb_runner.runner.custom_evaluator --scenario codegeneration --release_version release_v6
  --num_process_evaluate 16 --timeout 6"
wait_server() { for i in $(seq 1 120); do curl -s 127.0.0.1:$PORT/v1/models >/dev/null && return 0
  kill -0 $VP 2>/dev/null || return 1; sleep 10; done; return 1; }
stop_server() { kill $VP 2>/dev/null; sleep 20; pkill -f "port $PORT"; sleep 10; }
GEN="box /lcb/venv/bin/python /lcb/scripts/lcb_generate.py --url http://127.0.0.1:$PORT/v1/chat/completions --model $N
  --extra {} --ids /lcb/sweep/sweep_ids.json --out /lcb/sweep/$N.jsonl --max-tokens 16000 --workers 16 --timeout 7200"
echo "RETRY_START $N $(date -u)"
[ -f $S/$N.jsonl ] && [ ! -f $S/${N}_pilot8k.jsonl ] && mv $S/$N.jsonl $S/${N}_pilot8k.jsonl
$V serve $(snap $H/models--nvidia--NVIDIA-Nemotron-Nano-9B-v2) --served-model-name $N --port $PORT --host 127.0.0.1 \
  --max-model-len 32768 --gpu-memory-utilization 0.90 --trust-remote-code --mamba-ssm-cache-dtype float32 > $S/vllm_${N}_retry.log 2>&1 &
VP=$!
if ! wait_server; then echo "SERVER_FAILED $N"; stop_server; exit 1; fi
$GEN --limit 5
ok=$(python3 -c "import json;print(sum(bool((json.loads(l).get('code') or '').strip()) for l in open('$S/$N.jsonl')))")
if [ "$ok" -lt 3 ]; then echo "PILOT_FAIL $N ($ok of 5 with code)"; stop_server; exit 1; fi
$GEN; $GEN
echo "generated $N $(wc -l < $S/$N.jsonl) $(date -u)"
( box /lcb/venv/bin/python /lcb/scripts/lcb_generate.py --out /lcb/sweep/$N.jsonl --export /lcb/sweep/$N.json --fill-empty \
    && box $EVAL --custom_output_file /lcb/sweep/$N.json ) > $S/grade_$N.log 2>&1 &
python3 $S/lcb_sweep_prompts.py --existing $S/lcb_p1.jsonl --gen $S/$N.jsonl --writer $N --out $S/${N}_p1.jsonl
cat $S/${N}_p1.jsonl $S/lcb_p1.jsonl > $S/judge_$N.jsonl
for T in 8000 16000; do
  R=""; [ $T = 16000 ] && R=--redo-unparsed
  LOCAL_JUDGE_EXTRA='{}' python3 $S/local_judging.py run --base http://127.0.0.1:$PORT/v1 --model $N --tag $N \
      --prompts $S/judge_$N.jsonl --out $S/scores_$N.jsonl --workers 16 --max-tokens $T $R
done
touch $S/$N.judged; stop_server
echo "MODEL_DONE $N rows $(wc -l < $S/scores_$N.jsonl) $(date -u)"
$V serve $(snap $H/models--Qwen--Qwen3-32B) --served-model-name qwen3-32b --port $PORT --host 127.0.0.1 --max-model-len 32768 \
  --gpu-memory-utilization 0.95 > $S/vllm_qwen_retry.log 2>&1 &
VP=$!
if wait_server; then
  for T in 3000 8000; do
    R=""; [ $T = 8000 ] && R=--redo-unparsed
    LOCAL_JUDGE_NO_THINK=1 python3 $S/local_judging.py run --base http://127.0.0.1:$PORT/v1 --model qwen3-32b \
        --tag qwen3-32b-local --prompts $S/${N}_p1.jsonl --out $S/scores_qwen3-32b-local.jsonl --workers 16 --max-tokens $T $R
  done
else echo "SERVER_FAILED qwen3-32b"; fi
stop_server; wait
echo "RETRY_DONE $(date -u)"
