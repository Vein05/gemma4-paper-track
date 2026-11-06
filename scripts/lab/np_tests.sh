#!/bin/bash
# After the pilot's stop rule (spec/nonpython-rubber-stamp.md, addendum): rerun warning-affected issues, thinking-on test.
cd <workdir>/gemma4-paper-track/ml || exit 1
. ./env.sh
PY=<workdir>/swe-env/venv20/bin/python
USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
[ "$USED" -lt 2000 ] || { echo "GPU_BUSY ${USED} MiB $(date -u +%FT%TZ)"; exit 3; }
stop_vllm() {
  for p in $(pgrep -u "$USER" -f "[v]llm serve .*--port 18000"); do kill "$p"; done
  for i in $(seq 60); do pgrep -u "$USER" -f "[V]LLM::EngineCore" > /dev/null || break; sleep 5; done
  echo "vLLM stopped $(date -u +%FT%TZ)"
}
trap stop_vllm EXIT
GPU_UTIL=${GPU_UTIL:-0.70} bash serve_gemma4_tools.sh > runs/np_tests_vllm.log 2>&1 &
for i in $(seq 1 180); do curl -sf 127.0.0.1:18000/health > /dev/null && break; sleep 10; done
curl -sf 127.0.0.1:18000/health > /dev/null || { echo "SERVER_FAILED $(date -u +%FT%TZ)"; exit 1; }
echo "tests start $(date -u +%FT%TZ)"
[ -s np_rerun_ids.txt ] && timeout 75m $PY scripts/run_gemma_multilingual.py --issues "ids:$(paste -sd, np_rerun_ids.txt)" --out runs/nonpython --workers 3 > logs/np_rerun.log 2>&1 &
A=$!
[ -s np_think_ids.txt ] && timeout 75m $PY scripts/run_gemma_multilingual.py --issues "ids:$(paste -sd, np_think_ids.txt)" --out runs/np-thinking-test --workers 4 --thinking > logs/np_think.log 2>&1 &
B=$!
wait $A $B
echo "tests end $(date -u +%FT%TZ)"
stop_vllm; trap - EXIT
echo ALL_DONE
