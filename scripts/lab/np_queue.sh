#!/bin/bash
# Server-side GPU queue for 2026-11-06, from ml/ on the server. After the follow-up tests it applies the decision in
# spec/nonpython-rubber-stamp.md (patch counts only), then runs: repair seeds (spec/repair-seeds.md), the qualifying
# thinking-off groups, the Lite repair (spec/lite-repair-replication.md), and last any thinking-on arm.
cd <workdir>/gemma4-paper-track/ml || exit 1
E=<workdir>/swe-env
PY=$E/venv20/bin/python
wait_gpu() { until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)" -lt 2000 ]; do sleep 60; done; }
seed() {
  mkdir -p $E/test-repair/seed$1; cp -n $E/test-repair/run1/jobs.jsonl $E/test-repair/seed$1/
  wait_gpu; echo "seed $1 start $(date -u +%FT%TZ)"
  env -u SWE_DATASET OUT=seed$1 REPAIR_SEED=$1 REPAIR_TEMPERATURE=0.3 GPU_UTIL=0.70 WORKERS=8 bash $E/scripts/lab/test_repair_chain.sh
  echo "seed $1 end $(date -u +%FT%TZ)"
}
echo "queue start $(date -u +%FT%TZ)"
until grep -qE "^ALL_DONE|GPU_BUSY|SERVER_FAILED" logs/np_after_pilot.log; do sleep 30; done
sleep 30
$PY - <<'P'
import json, os
GO = ("caddyserver", "gin-gonic", "gohugoio", "hashicorp", "prometheus")
go_lang = lambda i: i.startswith(GO)
tests_ran = any(l.startswith("ALL_DONE") for l in open("logs/np_after_pilot.log"))
pilot = [l.strip() for l in open("np_pilot_ids.txt") if l.strip()]
everything = [l.strip() for l in open("np_ids.txt") if l.strip()]
preds = json.load(open("runs/nonpython/preds.json"))
has = lambda d, i: bool((d.get(i) or {}).get("model_patch"))
go = sum(has(preds, i) for i in pilot if go_lang(i))
other = sum(has(preds, i) for i in pilot if not go_lang(i))
think_ids = [l.strip() for l in open("np_think_ids.txt") if l.strip()] if os.path.exists("np_think_ids.txt") else []
tp = "runs/np-thinking-test/preds.json"
tpreds = json.load(open(tp)) if os.path.exists(tp) else {}
think = sum(has(tpreds, i) for i in think_ids)
go_ok, other_ok = tests_ran and go >= 2, other >= 3
think_ok = tests_ran and not other_ok and bool(think_ids) and think * 2 >= len(think_ids)
full = [i for i in everything if (go_ok and go_lang(i)) or (other_ok and not go_lang(i))]
arm = [i for i in everything if think_ok and not go_lang(i)]
open("np_full_ids.txt", "w").write("".join(i + "\n" for i in full))
open("np_think_arm_ids.txt", "w").write("".join(i + "\n" for i in arm))
d = dict(tests_ran=tests_ran, go_patches_of_3=go, php_ruby_patches_of_6=other, thinking_patches=think, thinking_issues=len(think_ids),
         go_qualifies=go_ok, php_ruby_qualifies=other_ok, thinking_arm_qualifies=think_ok, full_run_issues=len(full), thinking_arm_issues=len(arm))
json.dump(d, open("np_decision.json", "w"), indent=1); print("decision", d)
P
seed 1
seed 2
if [ -s np_full_ids.txt ]; then
  wait_gpu; echo "full run start $(date -u +%FT%TZ)"
  IDS_FILE=np_full_ids.txt OUT=runs/nonpython WORKERS=5 GRADE=1 CAP=6h bash nonpython_run.sh >> logs/np_full.log 2>&1
  echo "full run end $(date -u +%FT%TZ)"
fi
wait_gpu; touch $E/test-repair/lite_gpu_go; echo "Lite repair released $(date -u +%FT%TZ)"
until grep -q ALL_DONE $E/existing-test-gate-lite/chain.log || grep -q SERVER_FAILED $E/test-repair/lite/chain.log 2>/dev/null; do sleep 120; done
echo "Lite repair end $(date -u +%FT%TZ)"
if [ -s np_think_arm_ids.txt ]; then
  [ -d runs/nonpython-thinking ] || cp -r runs/np-thinking-test runs/nonpython-thinking
  wait_gpu; echo "thinking arm start $(date -u +%FT%TZ)"
  THINKING=1 IDS_FILE=np_think_arm_ids.txt OUT=runs/nonpython-thinking WORKERS=4 GRADE=1 CAP=8h bash nonpython_run.sh >> logs/np_think_arm.log 2>&1
  echo "thinking arm end $(date -u +%FT%TZ)"
fi
echo "QUEUE_DONE $(date -u +%FT%TZ)"
