#!/bin/bash
# Start the 12B pilot once the 26B-A4B pilot's agents are done and its vLLM server has stopped (spec addendum 2026-11-02).
S=<workdir>/gemma4-paper-track/sizes; cd $S || exit 1
echo "waiting for the 26B-A4B agents $(date -Is)"
until grep -q "agents done" logs/26b-pilot.log || grep -q "pilot ended" logs/chain-pilot.log; do sleep 60; done
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)" -lt 2000 ]; do sleep 30; done
echo "GPU free $(date -Is); starting the 12B pilot"
bash sizes_writers.sh run 12b data/pilot20.json runs/12b-pilot > logs/12b-pilot.log 2>&1
echo "12b pilot ended $(date -Is): $(grep -E 'STOP RULE|resolved .* of' logs/12b-pilot.log | tr '\n' ' ')"
