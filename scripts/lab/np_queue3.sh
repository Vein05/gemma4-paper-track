#!/bin/bash
# Replaces np_queue2.sh after the third addendum of spec/nonpython-rubber-stamp.md, from ml/ on the server:
# thinking-on arm on all 120 issues, then the Lite repair once the arm has released the GPU.
cd <workdir>/gemma4-paper-track/ml || exit 1
E=<workdir>/swe-env
wait_gpu() { until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)" -lt 2000 ]; do sleep 60; done; }
echo "third queue start $(date -u +%FT%TZ)"
if [ ! -d runs/nonpython-thinking ]; then cp -r runs/np-thinking-test runs/nonpython-thinking; fi
rm -f runs/nonpython-thinking/GPU_RELEASED
wait_gpu; echo "thinking arm start $(date -u +%FT%TZ)"
THINKING=1 IDS_FILE=np_think_arm_ids.txt OUT=runs/nonpython-thinking WORKERS=6 GRADE=1 CAP=8h bash nonpython_run.sh >> logs/np_think_arm.log 2>&1 &
ARM=$!
until [ -f runs/nonpython-thinking/GPU_RELEASED ] || ! kill -0 $ARM 2>/dev/null; do sleep 30; done
echo "thinking arm released the GPU $(date -u +%FT%TZ)"
wait_gpu; touch $E/test-repair/lite_gpu_go; echo "Lite repair released $(date -u +%FT%TZ)"
until grep -q ALL_DONE $E/existing-test-gate-lite/chain.log || grep -q SERVER_FAILED $E/test-repair/lite/chain.log 2>/dev/null; do sleep 120; done
echo "Lite repair end $(date -u +%FT%TZ)"
wait $ARM
echo "QUEUE_DONE $(date -u +%FT%TZ)"
