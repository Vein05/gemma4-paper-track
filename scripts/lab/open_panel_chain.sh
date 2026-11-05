#!/bin/bash
# Qwen3-32B as judge on SWE-bench Lite and LiveCodeBench (spec/open-panel-check.md). Same server settings and prompt as
# run_qwen_retry.sh (held-out). Log: probe/open_panel.log, ends with ALL_DONE or SERVER_FAILED.
cd <workdir>/gemma4-paper-track/probe
Q=<workdir>/hf-cache/hub/models--Qwen--Qwen3-32B/snapshots/9216db5781bf21249d130ec9da846c4624c16137
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
echo "start $(date -u)"
../.venv-vllm/bin/vllm serve $Q --served-model-name qwen3-32b --port 18011 --host 127.0.0.1 --max-model-len 32768 --gpu-memory-utilization 0.95 > vllm_qwen_open.log 2>&1 &
VP=$!
for i in $(seq 1 120); do curl -s 127.0.0.1:18011/v1/models >/dev/null && break; sleep 10; done
curl -s 127.0.0.1:18011/v1/models >/dev/null || { echo SERVER_FAILED; exit 1; }
for S in lite lcb; do
  echo "judge $S $(date -u)"
  LOCAL_JUDGE_NO_THINK=1 python3 local_judging.py run --base http://127.0.0.1:18011/v1 --model qwen3-32b --tag qwen3-32b-local --prompts ${S}_p1.jsonl --out ${S}_qwen3-32b-local.jsonl --workers 16 --max-tokens 3000
  LOCAL_JUDGE_NO_THINK=1 python3 local_judging.py run --base http://127.0.0.1:18011/v1 --model qwen3-32b --tag qwen3-32b-local --prompts ${S}_p1.jsonl --out ${S}_qwen3-32b-local.jsonl --workers 16 --max-tokens 8000 --redo-unparsed
  echo "rows $S $(wc -l < ${S}_qwen3-32b-local.jsonl)"
done
kill $VP; sleep 20; pkill -f "served-model-name qwen3-32b"
echo "ALL_DONE $(date -u)"
