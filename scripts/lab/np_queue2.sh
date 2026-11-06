#!/bin/bash
# Replaces np_queue.sh after the second addendum of spec/nonpython-rubber-stamp.md, from ml/ on the server. Seed 1 is already
# running. Then: seed 2, Go test with the working fix, Go if it qualifies, Lite repair, thinking-on arm.
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
echo "second queue start $(date -u +%FT%TZ)"
until [ -f $E/test-repair/seed1/GPU_RELEASED ] || grep -q SERVER_FAILED $E/test-repair/seed1/chain.log; do sleep 30; done
echo "seed 1 released the GPU $(date -u +%FT%TZ)"
seed 2

cp -n np_decision.json np_decision_before_second_fix.json
$PY - <<'P'
import json, os, shutil
ids = ["caddyserver__caddy-5626", "hashicorp__terraform-34580"]
preds = json.load(open("runs/nonpython/preds.json"))
os.makedirs("runs/nonpython-before-second-fix", exist_ok=True)
for i in ids:
    preds.pop(i, None)
    if os.path.exists(f"runs/nonpython/{i}"):
        shutil.move(f"runs/nonpython/{i}", f"runs/nonpython-before-second-fix/{i}")
json.dump(preds, open("runs/nonpython/preds.json", "w"), indent=1)
open("np_go_retest_ids.txt", "w").write("".join(i + "\n" for i in ids))
P
wait_gpu; echo "Go test start $(date -u +%FT%TZ)"
IDS_FILE=np_go_retest_ids.txt OUT=runs/nonpython WORKERS=2 GRADE=0 CAP=75m bash nonpython_run.sh >> logs/np_go_retest.log 2>&1
echo "Go test end $(date -u +%FT%TZ)"

GO_FAILED=$($PY - <<'P'
import json
pilot = [l.strip() for l in open("np_pilot_ids.txt") if l.strip()]
preds = json.load(open("runs/nonpython/preds.json"))
go = [i for i in pilot if i.startswith(("caddyserver", "gin-gonic", "gohugoio", "hashicorp", "prometheus"))]
empty = [i for i in go if not (preds.get(i) or {}).get("model_patch")]
open("np_go_think_ids.txt", "w").write("".join(i + "\n" for i in empty))
print(int(len(go) - len(empty) < 2))
P
)
if [ "$GO_FAILED" = 1 ]; then
  wait_gpu; echo "Go thinking-on test start $(date -u +%FT%TZ)"
  THINKING=1 IDS_FILE=np_go_think_ids.txt OUT=runs/np-thinking-test WORKERS=3 GRADE=0 CAP=45m bash nonpython_run.sh >> logs/np_go_think.log 2>&1
  echo "Go thinking-on test end $(date -u +%FT%TZ)"
fi

$PY - <<'P'
import json
GO = ("caddyserver", "gin-gonic", "gohugoio", "hashicorp", "prometheus")
go_lang = lambda i: i.startswith(GO)
read = lambda f: [l.strip() for l in open(f) if l.strip()]
pilot, everything = read("np_pilot_ids.txt"), read("np_ids.txt")
preds = json.load(open("runs/nonpython/preds.json"))
tpreds = json.load(open("runs/np-thinking-test/preds.json"))
has = lambda d, i: bool((d.get(i) or {}).get("model_patch"))
go = sum(has(preds, i) for i in pilot if go_lang(i))
other = sum(has(preds, i) for i in pilot if not go_lang(i))
think_ids = [i for i in read("np_think_ids.txt")]
think = sum(has(tpreds, i) for i in think_ids)
go_ok, other_ok = go >= 2, other >= 3
go_think_ids = read("np_go_think_ids.txt") if not go_ok else []
go_think = sum(has(tpreds, i) for i in go_think_ids)
other_arm = not other_ok and think * 2 >= len(think_ids)
go_arm = not go_ok and bool(go_think_ids) and go_think * 2 >= len(go_think_ids)
full = [i for i in everything if (go_ok and go_lang(i)) or (other_ok and not go_lang(i))]
arm = [i for i in everything if (go_arm and go_lang(i)) or (other_arm and not go_lang(i))]
open("np_full_ids.txt", "w").write("".join(i + "\n" for i in full))
open("np_think_arm_ids.txt", "w").write("".join(i + "\n" for i in arm))
d = dict(go_patches_of_3=go, php_ruby_patches_of_6=other, php_ruby_thinking=[think, len(think_ids)], go_thinking=[go_think, len(go_think_ids)],
         go_qualifies=go_ok, php_ruby_qualifies=other_ok, php_ruby_arm=other_arm, go_arm=go_arm, full_run_issues=len(full), thinking_arm_issues=len(arm))
json.dump(d, open("np_decision.json", "w"), indent=1); print("decision", d)
P

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
  THINKING=1 IDS_FILE=np_think_arm_ids.txt OUT=runs/nonpython-thinking WORKERS=6 GRADE=1 CAP=8h bash nonpython_run.sh >> logs/np_think_arm.log 2>&1
  echo "thinking arm end $(date -u +%FT%TZ)"
fi
echo "QUEUE_DONE $(date -u +%FT%TZ)"
