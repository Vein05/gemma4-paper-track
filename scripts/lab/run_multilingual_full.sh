#!/bin/bash
# Full SWE-bench Multilingual run on the lab A100 (spec/multilingual-replication.md), from ml/ on the server:
#   (cd <workdir>/gemma4-paper-track/ml; nohup bash run_multilingual_full.sh > logs/ml_main.log 2>&1 &)
# 1. Gemma's agents on all 300 issues (2 workers: 5 overflowed vLLM's prefix cache in the smoke test, 2026-10-23).
# 2. Stop our vLLM server on port 18000, however step 1 ended, so the shared GPU is not held while idle.
# 3. Grade Gemma's patches on the CPUs.
# Every step resumes: rerunning the script skips finished issues and graded patches (vLLM must be started again).
cd <workdir>/gemma4-paper-track/ml || exit 1
. ./env.sh
PY=<workdir>/swe-env/venv20/bin/python
OUT=runs/ml-main
DS=data/public/swe-bench-multilingual/data/test-00000-of-00001.parquet

stop_vllm() {
  for p in $(pgrep -u "$USER" -f "[v]llm serve .*--port 18000"); do kill "$p"; done
  for i in $(seq 60); do pgrep -u "$USER" -f "[V]LLM::EngineCore" > /dev/null || break; sleep 5; done
  echo "vLLM stopped $(date -Is); our GPU processes left: $(pgrep -u "$USER" -f "[V]LLM::EngineCore" | wc -l)"
}
trap stop_vllm EXIT

echo "agents start $(date -Is)"
$PY scripts/run_gemma_multilingual.py --issues order:0-300 --out $OUT --workers 2
echo "agents end $(date -Is), exit $?"
stop_vllm

$PY - $OUT <<'PY'
import json, sys
out = sys.argv[1]
preds = json.load(open(f"{out}/preds.json"))
with open(f"{out}/preds.jsonl", "w") as f:
    for iid, p in sorted(preds.items()):
        f.write(json.dumps(dict(instance_id=iid, model_patch=p.get("model_patch") or "")) + "\n")
print(f"{len(preds)} predictions")
PY
$PY scripts/eval_apptainer.py eval --dataset $DS --preds $OUT/preds.jsonl --out $OUT/labels.jsonl --workers 4
echo "grading end $(date -Is), exit $?"
