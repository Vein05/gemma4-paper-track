#!/bin/bash
#SBATCH -J vein05-gemma
#SBATCH -p gpuq
#SBATCH --gpus 1
#SBATCH -c 16
#SBATCH --mem 128g
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%j.out
# Gemma 4 agent runs and SWE-bench labels on one MCSR Magnolia L40S (spec/fresh-replication.md).
# vLLM serves the competition checkpoint inside the job; mini-SWE-agent workers and their Apptainer sandboxes run on
# the same node; the finished patches are graded in the same job.
#
#   sbatch --export=ALL,ISSUES=pilot,OUT=runs/pilot run_pilot.sbatch                                   # pilot
#   sbatch -d afterok:<pilot job> --export=ALL,ISSUES=order:0-100,OUT=runs/main-a,GATE=runs/pilot run_pilot.sbatch  # main
#   sbatch -t 00:30:00 --export=ALL,ISSUES=ids:django__django-16569,OUT=runs/smoke,STEPS=20 run_pilot.sbatch  # smoke
set -euo pipefail
cd ~/vein05
ISSUES=${ISSUES:?ISSUES}; OUT=${OUT:?OUT}; STEPS=${STEPS:-}; WORKERS=${WORKERS:-5}; MAXLEN=${MAXLEN:-131072}
export HF_HOME=$PWD/hf HF_HUB_OFFLINE=1 TMPDIR=$PWD/tmp WORK=$PWD/work/$SLURM_JOB_ID
export APPTAINER_CACHEDIR=$PWD/apptainer/cache APPTAINER_TMPDIR=$PWD/apptainer/tmp
export APPTAINER_EXEC_FLAGS="" APPTAINER_MOUNT_DIRS=/ddnlus VLLM_BASE=http://127.0.0.1:18000/v1
export MODEL_REVISION=52f3f65bc7a02d555763bc923bd1d9094898219d  # Hugging Face snapshot downloaded 2026-10-05
mkdir -p $TMPDIR $WORK $APPTAINER_CACHEDIR $APPTAINER_TMPDIR $OUT
# FlashInfer compiles kernels at first use and needs nvcc: load the toolkit that matches torch (CUDA 13.0), and use
# PyTorch's sampler (temperature 0 is greedy, so the sampler choice does not change outputs)
source /etc/profile.d/modules.sh 2>/dev/null || true
module load cuda13.0/toolkit/13.0.2 2>/dev/null && export CUDA_HOME=$(dirname $(dirname $(which nvcc)))
export VLLM_USE_FLASHINFER_SAMPLER=0
source venv/bin/activate
echo "job $SLURM_JOB_ID on $(hostname) $(date -Is) issues=$ISSUES out=$OUT steps=${STEPS:-config} maxlen=$MAXLEN"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
echo "nvcc: $(which nvcc 2>/dev/null || echo none)"
python -c "import importlib.metadata as m; print({p: m.version(p) for p in ['vllm','torch','mini-swe-agent','swebench','litellm']})"

# main-run jobs: stop unless the pilot met the spec's rule (resolve rate >= 10%, median run <= 30 minutes)
if [ -n "${GATE:-}" ]; then
  python - "$GATE" <<'PY' || { echo "pilot gate not met; main run not started"; exit 0; }
import json, statistics, sys
g = sys.argv[1]
p = [json.loads(l) for l in open(f"{g}/preds.jsonl")]
lab = {r["instance_id"]: r.get("resolved") for r in map(json.loads, open(f"{g}/labels.jsonl"))}
rate = sum(bool(lab.get(r["instance_id"])) for r in p) / len(p)
med = statistics.median(r["seconds"] for r in p) / 60
print(f"pilot gate: resolve rate {rate:.2f}, median {med:.1f} min, n={len(p)}")
sys.exit(0 if rate >= 0.10 and med <= 30 else 1)
PY
fi

vllm serve google/gemma-4-31B-it-qat-w4a16-ct --revision "$MODEL_REVISION" --served-model-name gemma4-qat --port 18000 \
  --max-model-len "$MAXLEN" --gpu-memory-utilization 0.90 --max-num-seqs 8 --enable-prefix-caching \
  --reasoning-parser gemma4 > "$OUT/vllm.log" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null; rm -rf "$WORK"' EXIT
for i in $(seq 120); do
  curl -sf http://127.0.0.1:18000/health >/dev/null && break
  kill -0 $VLLM_PID 2>/dev/null || { echo "vLLM exited"; tail -40 "$OUT/vllm.log"; exit 1; }
  sleep 10
done
curl -sf http://127.0.0.1:18000/health >/dev/null || { echo "vLLM not up after 20 min"; tail -40 "$OUT/vllm.log"; exit 1; }
echo "vLLM up $(date -Is)"; grep -m2 -E "KV cache|maximum concurrency" "$OUT/vllm.log" || true

python scripts/run_gemma_mini.py --issues "$ISSUES" --out "$OUT" --workers "$WORKERS" ${STEPS:+--step-limit $STEPS}
echo "agents done $(date -Is)"
python scripts/eval_apptainer.py eval --preds "$OUT/preds.jsonl" --out "$OUT/labels.jsonl" --workers "$WORKERS"
echo "grading done $(date -Is)"
python - "$OUT" <<'PY'
import json, statistics, sys
out = sys.argv[1]
p = [json.loads(l) for l in open(f"{out}/preds.jsonl")]
lab = {r["instance_id"]: r for r in map(json.loads, open(f"{out}/labels.jsonl"))}
for r in p:
    print(r["instance_id"], r["exit_status"], f"calls={r['n_calls']}", f"{r['seconds']}s", "resolved", lab.get(r["instance_id"], {}).get("resolved"))
print("resolved", sum(bool(lab.get(r["instance_id"], {}).get("resolved")) for r in p), "of", len(p),
      "| median minutes", round(statistics.median(r["seconds"] for r in p) / 60, 1))
PY
