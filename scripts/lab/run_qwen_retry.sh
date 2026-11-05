#!/bin/bash
# Qwen3-32B judge retry (addendum 7). The first try failed at startup: bf16 weights took 61 GiB and left 7.6 GiB of
# KV cache, too little for 40960 tokens. Waits for the sampling run to finish, then serves at 32768 tokens, 0.95 memory.
cd <workdir>/gemma4-paper-track/probe
until grep -q "ALL_DONE" run_sampling.log 2>/dev/null; do sleep 60; done
sleep 20
P=../.venv-probe/bin/python
Q=<workdir>/seam/hf/hub/models--Qwen--Qwen3-32B/snapshots/9216db5781bf21249d130ec9da846c4624c16137
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
[ -f fresh_qwen3-32b-local.jsonl ] && mv -f fresh_qwen3-32b-local.jsonl fresh_qwen3-32b-local.failed-start.jsonl
../.venv-vllm/bin/vllm serve $Q --served-model-name qwen3-32b --port 18011 --host 127.0.0.1 --max-model-len 32768 --gpu-memory-utilization 0.95 > vllm_qwen.log 2>&1 &
VP=$!
for i in $(seq 1 120); do curl -s 127.0.0.1:18011/v1/models >/dev/null && break; sleep 10; done
curl -s 127.0.0.1:18011/v1/models >/dev/null || { echo SERVER_FAILED; exit 1; }
LOCAL_JUDGE_NO_THINK=1 python3 local_judging.py run --base http://127.0.0.1:18011/v1 --model qwen3-32b --tag qwen3-32b-local --prompts heldout_p1.jsonl --out fresh_qwen3-32b-local.jsonl --workers 16 --max-tokens 3000 > judge_qwen.log 2>&1
LOCAL_JUDGE_NO_THINK=1 python3 local_judging.py run --base http://127.0.0.1:18011/v1 --model qwen3-32b --tag qwen3-32b-local --prompts heldout_p1.jsonl --out fresh_qwen3-32b-local.jsonl --workers 16 --max-tokens 8000 --redo-unparsed >> judge_qwen.log 2>&1
kill $VP; sleep 20; pkill -f "served-model-name qwen3-32b"; sleep 10
echo JUDGE_DONE
python3 build_prefix.py fresh_qwen3-32b-local.jsonl heldout_answers_qwen3-32b.jsonl
rm -rf score_qwen32b
$P probe_extract.py score --model $Q --prompts heldout_p1.jsonl --answers heldout_answers_qwen3-32b.jsonl --out score_qwen32b && echo ALL_DONE
