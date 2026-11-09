#!/bin/zsh
# Stage 1 of spec/matched-writers.md: nine judges on derived/matched_patches.jsonl, a 3,000-token pass and then the
# 8,000-token ask for unparsed answers. Stops every judge if the summed cost in the row files passes $8.
cd <repo>/scripts
mkdir -p logs
pids=()
for t in gemma4-31b gpt-oss-20b qwen35-9b glm47-flash qwen3-coder gpt-oss-120b glm-4.5 kimi-k2 llama-4-maverick; do
  ( python3 matched_writers.py run --tag $t --workers 24 >> logs/matched_$t.log 2>&1
    python3 matched_writers.py run --tag $t --workers 24 --redo-unparsed --max-tokens 8000 >> logs/matched_$t.log 2>&1
    echo "$t done" >> logs/matched_all.log ) &
  pids+=($!)
done
( while sleep 30; do
    c=$(cat derived/matched_*.jsonl 2>/dev/null | python3 -c "
import sys, json
print(sum((json.loads(l).get('cost') or 0) for l in sys.stdin))")
    echo "$(date -u +%H:%M:%S) cost $c" >> logs/matched_cost.log
    if python3 -c "import sys; sys.exit(0 if float('$c') > 8 else 1)"; then
      echo "SPEND GUARD at $c" >> logs/matched_all.log; pkill -f "matched_writers.py run"; break
    fi
  done ) &
guard=$!
wait $pids  # the judges only; waiting on every job would also wait on the cost guard, which never ends
kill $guard 2>/dev/null
echo ALL_DONE >> logs/matched_all.log
