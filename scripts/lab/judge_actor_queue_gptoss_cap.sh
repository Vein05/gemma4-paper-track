#!/bin/bash
# Spec addendum 2: after the Gemma testbed queue ends, rerun the one unfinished gpt-oss-20b pilot issue with a
# 32,768-token reply cap. Log ends CAP_DONE or CAP_STOPPED <reason>.
set -uo pipefail
E=<workdir>/swe-env
L=$E/logs
echo "cap queue start $(date -u +%FT%TZ)"
until grep -qE "QUEUE_DONE|QUEUE_STOPPED" $L/judge_queue_gemma.log 2>/dev/null; do sleep 60; done
echo "gemma queue ended: $(grep -E 'QUEUE_DONE|QUEUE_STOPPED' $L/judge_queue_gemma.log | tail -1) $(date -u +%FT%TZ)"
for i in $(seq 1 60); do curl -sf 127.0.0.1:18000/health >/dev/null || break; sleep 10; done
curl -sf 127.0.0.1:18000/health >/dev/null && { echo "CAP_STOPPED port 18000 busy"; exit 1; }
[ -f $E/judge-as-actor/gptoss/vllm-pilot-1.log ] || cp $E/judge-as-actor/gptoss/vllm.log $E/judge-as-actor/gptoss/vllm-pilot-1.log
cd $E/scripts/lab
JUDGE=gptoss SETS=pilot IDS=pylint-dev__pylint-8898 MAX_TOKENS=32768 bash judge_actor_chain.sh > $L/judge_pilot_gptoss_cap.log 2>&1
echo "CAP_DONE $(tail -1 $L/judge_pilot_gptoss_cap.log) $(date -u +%FT%TZ)"
