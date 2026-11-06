#!/bin/bash
# Gemma 4 agents on Go, Ruby and PHP issues (spec/nonpython-rubber-stamp.md), lab A100, from ml/ on the server:
#   IDS_FILE=np_pilot_ids.txt OUT=runs/nonpython WORKERS=4 GRADE=0 nohup bash nonpython_run.sh > logs/np.log 2>&1 &
# Serves vLLM only if the GPU is idle, stops it however the agents end, then grades on the CPUs when GRADE=1. Resumes.
cd <workdir>/gemma4-paper-track/ml || exit 1
. ./env.sh
PY=<workdir>/swe-env/venv20/bin/python
OUT=${OUT:?OUT}
DS=data/public/swe-bench-multilingual/data/test-00000-of-00001.parquet
mkdir -p $OUT
USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
[ "$USED" -lt 2000 ] || { echo "GPU_BUSY ${USED} MiB $(date -u +%FT%TZ)"; exit 3; }
stop_vllm() {
  for p in $(pgrep -u "$USER" -f "[v]llm serve .*--port 18000"); do kill "$p"; done
  for i in $(seq 60); do pgrep -u "$USER" -f "[V]LLM::EngineCore" > /dev/null || break; sleep 5; done
  echo "vLLM stopped $(date -u +%FT%TZ)"
}
trap stop_vllm EXIT
GPU_UTIL=${GPU_UTIL:-0.70} bash serve_gemma4_tools.sh > $OUT/vllm.log 2>&1 &
for i in $(seq 1 180); do curl -sf 127.0.0.1:18000/health > /dev/null && break; sleep 10; done
curl -sf 127.0.0.1:18000/health > /dev/null || { echo "SERVER_FAILED $(date -u +%FT%TZ)"; tail -30 $OUT/vllm.log; exit 1; }
echo "agents start $(date -u +%FT%TZ)"
timeout ${CAP:-8h} $PY scripts/run_gemma_multilingual.py --issues "ids:$(paste -sd, $IDS_FILE)" --out $OUT --workers ${WORKERS:-4} ${THINKING:+--thinking}
echo "agents end $(date -u +%FT%TZ), exit $?"
stop_vllm
trap - EXIT
touch $OUT/GPU_RELEASED
[ "${GRADE:-0}" = 1 ] || { echo ALL_DONE; exit 0; }
$PY - $OUT <<'PY'
import json, sys
out = sys.argv[1]
preds = json.load(open(f"{out}/preds.json"))
with open(f"{out}/preds.jsonl", "w") as f:
    for iid, p in sorted(preds.items()):
        f.write(json.dumps(dict(instance_id=iid, model_patch=p.get("model_patch") or "")) + "\n")
print(f"{len(preds)} predictions")
PY
$PY scripts/eval_apptainer.py eval --dataset $DS --preds $OUT/preds.jsonl --out $OUT/labels.jsonl --workers 12
echo "ALL_DONE $(date -u +%FT%TZ)"
