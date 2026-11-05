#!/bin/bash
# Queue (2026-11-03): after the gpt-oss-20b pilot, rerun the Gemma actor pilot with the testbed environment active.
# Waits for the gpt-oss chain to end and port 18000 to be free, runs the Gemma smoke test on the two smoke issues,
# checks it, then runs the pilot on the 133 stamped own patches. Log ends QUEUE_DONE or QUEUE_STOPPED <reason>.
set -uo pipefail
E=<workdir>/swe-env; L=$E/logs; cd $E/scripts/lab
echo "queue start $(date -u +%FT%TZ)"
until grep -qE "ALL_DONE|SERVER_FAILED" $L/judge_pilot_gptoss.log; do sleep 60; done
echo "gpt-oss chain ended: $(grep -E 'ALL_DONE|SERVER_FAILED' $L/judge_pilot_gptoss.log) $(date -u +%FT%TZ)"
for i in $(seq 1 30); do curl -sf 127.0.0.1:18000/health >/dev/null || break; sleep 10; done
curl -sf 127.0.0.1:18000/health >/dev/null && { echo "QUEUE_STOPPED port 18000 still serving"; exit 1; }
[ -e $E/judge-as-actor/gemma ] && { echo "QUEUE_STOPPED judge-as-actor/gemma exists (old rows would be skipped)"; exit 1; }
GPU_UTIL=0.78 JUDGE=gemma SETS=pilot IDS=astropy__astropy-14508,astropy__astropy-7166 STEPS=15 \
  bash judge_actor_chain.sh > $L/judge_smoke_gemma_testbed.log 2>&1
tail -1 $L/judge_smoke_gemma_testbed.log
python3 - <<'PY' || { echo "QUEUE_STOPPED smoke check failed"; exit 1; }
import json, glob, re, sys
d = "<workdir>/swe-env/judge-as-actor/gemma"
rows = [json.loads(l) for l in open(d + "/runs.jsonl")]
bad = []
if len(rows) != 2: bad.append(f"{len(rows)} rows")
for r in rows:
    if r.get("score") is None: bad.append(f"{r['iid']} no score ({r['status']})")
    if not isinstance(r.get("test_applied"), dict) or r["test_applied"].get("status") != "ran": bad.append(f"{r['iid']} test not run")
for f in glob.glob(d + "/trajs/*.json"):
    m = json.load(open(f))["messages"]
    outs = " ".join(x["content"] for x in m[2:] if x["role"] == "user")
    if re.search(r"miniconda3/lib/python3\.11|No module named 'erfa'", outs): bad.append(f"{f[-40:]} base python")
for r in rows:
    print("smoke", r["iid"], r["status"], r.get("score"), r.get("n_calls"),
          (r.get("test_reverted") or {}).get("passes"), (r.get("test_applied") or {}).get("passes"))
print("SMOKE_BAD" if bad else "SMOKE_OK", bad)
sys.exit(1 if bad else 0)
PY
GPU_UTIL=0.78 JUDGE=gemma SETS=pilot bash judge_actor_chain.sh > $L/judge_pilot_gemma_testbed.log 2>&1
echo "pilot: $(tail -1 $L/judge_pilot_gemma_testbed.log)"
echo "QUEUE_DONE $(date -u +%FT%TZ)"
