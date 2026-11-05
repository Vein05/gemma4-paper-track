#!/bin/bash
# Chain for the 26B-A4B pilot (spec/gemma-sizes-writers.md), from sizes/ on the lab server:
#   nohup bash sizes_chain_pilot.sh > logs/chain-pilot.log 2>&1 &
# 1. wait for the image pull to end; 2. grade the reference patches (CPU); 3. wait until the writing project's job
# has written ALL_DONE (it holds the A100 until about 00:30, message of 2026-11-01) and under 2 GB of GPU memory is in
# use; 4. run the 26B-A4B pilot.
cd <workdir>/gemma4-paper-track/sizes || exit 1
W=<workdir>/writeguard-research/experiments/many-papers-writer-2026-11-01/logs_full.log
while pgrep -u "$USER" -f "sizes_writers.sh pull" > /dev/null; do sleep 60; done
echo "pull ended $(date -Is): $(tail -1 logs/pull-pilot20.log)"
bash sizes_writers.sh gold data/pilot20.json runs/gold-pilot20 > logs/gold-pilot20.log 2>&1
echo "gold ended $(date -Is): $(grep 'reference patches resolved' logs/gold-pilot20.log)"
while true; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  done_w=$(tail -c 200 "$W" 2>/dev/null | grep -c ALL_DONE)
  if [ "$done_w" -ge 1 ] && [ "$used" -lt 2000 ]; then break; fi
  sleep 120
done
echo "GPU free $(date -Is) (${used} MiB used); starting the 26B-A4B pilot"
bash sizes_writers.sh run 26b data/pilot20.json runs/26b-pilot > logs/26b-pilot.log 2>&1
echo "pilot ended $(date -Is)"
tail -3 logs/26b-pilot.log
