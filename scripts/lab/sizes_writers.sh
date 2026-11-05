#!/bin/bash
# Gemma 4 12B and 26B-A4B as patch writers on the held-out issues, lab A100 (spec/gemma-sizes-writers.md).
# Server folder: <workdir>/gemma4-paper-track/sizes (scripts/, data/, runs/, logs/). Run from there:
#   bash sizes_writers.sh pull <ids.json>        pull each issue's image once into SIF_DIR (CPU, no GPU)
#   bash sizes_writers.sh gold <ids.json> <out>  grade the reference patches of these issues here (CPU)
#   bash sizes_writers.sh run <size> <ids.json> <out>
#        size = 26b | 12b: start vLLM on port 18000, run mini-SWE-agent 1.7.0 on the issues, stop vLLM, grade
#   bash sizes_writers.sh gate <out>             the pilot's stop rule
# Long steps: nohup bash sizes_writers.sh run 26b data/pilot20.json runs/26b-pilot > logs/26b-pilot.log 2>&1 &
# Every step resumes: rerunning skips pulled images, finished issues and graded patches.
set -uo pipefail
S=<workdir>/gemma4-paper-track/sizes
B=<workdir>/gemma4-paper-track
cd $S || exit 1
export APPTAINER=<workdir>/swe-env/apptainer/bin/apptainer PATH=<workdir>/swe-env/apptainer/bin:$PATH
export APPTAINER_CACHEDIR=<workdir>/swe-env/cache APPTAINER_TMPDIR=<workdir>/swe-env/tmp
export WORK=$S/work TMPDIR=$S/work HF_HOME=<workdir>/swe-env/hf HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-0}
export APPTAINER_EXEC_FLAGS="--fakeroot --ignore-subuid"  # as the 2026-10-05 lab validation on Verified images
export SIF_DIR=<workdir>/swe-env/sif VLLM_BASE=http://127.0.0.1:18000/v1
PY=<workdir>/swe-env/venv17/bin/python  # mini-SWE-agent 1.7.0, swebench 4.1.0 (the 31B's versions)
mkdir -p $WORK logs runs

stop_vllm() {
  for p in $(pgrep -u "$USER" -f "[v]llm serve .*--port 18000"); do kill "$p"; done
  for i in $(seq 60); do pgrep -u "$USER" -f "[V]LLM::EngineCore" > /dev/null || break; sleep 5; done
  echo "vLLM stopped $(date -Is); our GPU processes left: $(pgrep -u "$USER" -f "[V]LLM::EngineCore" | wc -l)"
}

serve() {  # same flags as the 31B's runs (scripts/mcsr/run_pilot.sbatch) unless noted
  export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
  export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_NO_USAGE_STATS=1
  local V=$B/.venv-vllm/bin/vllm common="--port 18000 --host 127.0.0.1 --max-model-len 131072 --gpu-memory-utilization 0.90
    --max-num-seqs 8 --enable-prefix-caching --reasoning-parser gemma4 --limit-mm-per-prompt {\"image\":0,\"audio\":0}"
  case $1 in
    26b)  # bf16 weights served in fp8, eager mode, CUTLASS fp8 off: the A100 settings of ml/serve_gemma4_26b.sh
      export VLLM_DISABLED_KERNELS=CutlassFP8ScaledMMLinearKernel
      export SERVED_MODEL=gemma4-26b-a4b MODEL_ID=google/gemma-4-26B-A4B-it
      $V serve $B/models/gemma-4-26B-A4B-it --served-model-name $SERVED_MODEL --quantization fp8 --enforce-eager $common ;;
    12b)
      export SERVED_MODEL=gemma4-12b MODEL_ID=google/gemma-4-12B-it-qat-w4a16-ct
      $V serve $B/models/gemma-4-12B-it-qat-w4a16-ct --served-model-name $SERVED_MODEL $common ;;
    *) echo "size must be 26b or 12b"; return 1 ;;
  esac
}

case ${1:-} in
pull)
  $PY - "$2" <<'PY'
import concurrent.futures as cf, json, sys, time
sys.path.insert(0, "scripts")
from eval_apptainer import image
ids = json.load(open(sys.argv[1]))
t0 = time.time()
def one(i):
    try:
        return i, image(i)
    except Exception as e:
        return i, f"FAILED {e}"
with cf.ThreadPoolExecutor(4) as ex:
    for i, r in ex.map(one, ids):
        print(i, r, flush=True)
print(f"pulled {len(ids)} in {time.time() - t0:.0f}s")
PY
  ;;
gold)
  mkdir -p "$3"
  $PY - "$2" "$3/preds.jsonl" <<'PY'
import json, sys
from datasets import load_dataset
ids = set(json.load(open(sys.argv[1])))
with open(sys.argv[2], "w") as f:
    for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test"):
        if r["instance_id"] in ids:
            f.write(json.dumps(dict(instance_id=r["instance_id"], model_patch=r["patch"])) + "\n")
PY
  $PY scripts/eval_apptainer.py eval --preds "$3/preds.jsonl" --out "$3/labels.jsonl" --workers 4
  $PY -c "import json,sys; L=[json.loads(l) for l in open(sys.argv[1])]; print('reference patches resolved', sum(bool(x['resolved']) for x in L), 'of', len(L)); [print(x['instance_id'], x['status'], x['resolved']) for x in L if not x['resolved']]" "$3/labels.jsonl"
  ;;
run)
  SIZE=$2 IDS=$3 OUT=$4
  mkdir -p "$OUT"
  free=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  echo "start $(date -Is) size=$SIZE ids=$IDS out=$OUT; GPU memory used before start: ${free} MiB"
  [ "$free" -gt 2000 ] && { echo "GPU busy (${free} MiB used; vLLM needs 71.2 GiB free); not starting"; exit 1; }
  trap stop_vllm EXIT
  serve "$SIZE" > "$OUT/vllm.log" 2>&1 &
  for i in $(seq 120); do
    curl -sf http://127.0.0.1:18000/health > /dev/null && break
    pgrep -u "$USER" -f "[v]llm serve .*--port 18000" > /dev/null || { echo "vLLM exited"; tail -40 "$OUT/vllm.log"; exit 1; }
    sleep 10
  done
  curl -sf http://127.0.0.1:18000/health > /dev/null || { echo "vLLM not up after 20 min"; tail -40 "$OUT/vllm.log"; exit 1; }
  echo "vLLM up $(date -Is)"; grep -m2 -E "KV cache|maximum concurrency" "$OUT/vllm.log"
  case $SIZE in  # revisions downloaded 2026-10-23 (ml/judge-sizes/revisions.txt)
    26b) export SERVED_MODEL=gemma4-26b-a4b MODEL_ID=google/gemma-4-26B-A4B-it
         export MODEL_REVISION=4d7ae4984b7db7de8f8457170b3f1a419ee76d52 ;;
    12b) export SERVED_MODEL=gemma4-12b MODEL_ID=google/gemma-4-12B-it-qat-w4a16-ct
         export MODEL_REVISION=1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee ;;
  esac
  $PY scripts/run_gemma_mini.py --issues "ids-file:$IDS" --out "$OUT" --workers ${WORKERS:-5}
  echo "agents done $(date -Is)"
  stop_vllm
  trap - EXIT
  $PY scripts/eval_apptainer.py eval --preds "$OUT/preds.jsonl" --out "$OUT/labels.jsonl" --workers 4
  echo "grading done $(date -Is)"
  bash "$0" gate "$OUT"
  ;;
gate)
  $PY - "$2" <<'PY'
import json, statistics, sys
out = sys.argv[1]
p = [json.loads(l) for l in open(f"{out}/preds.jsonl")]
lab = {r["instance_id"]: r for r in map(json.loads, open(f"{out}/labels.jsonl"))}
for r in p:
    print(r["instance_id"], r["exit_status"], f"calls={r['n_calls']}", f"{r['seconds']}s",
          "resolved", lab.get(r["instance_id"], {}).get("resolved"))
n = len(p)
res = sum(bool(lab.get(r["instance_id"], {}).get("resolved")) for r in p)
sub = sum(r["exit_status"] == "Submitted" and bool(r["model_patch"].strip()) for r in p)
med = statistics.median(r["seconds"] for r in p) / 60
print(f"resolved {res} of {n} ({res / n:.0%}); submitted a patch {sub} of {n} ({sub / n:.0%}); median {med:.1f} min")
ok = res / n >= 0.10 and sub / n >= 0.85
print("STOP RULE:", "passed, the full run may start" if ok else "NOT passed, no full run")
PY
  ;;
*) sed -n 2,12p "$0" ;;
esac
