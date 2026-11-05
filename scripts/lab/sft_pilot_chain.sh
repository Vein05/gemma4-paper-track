#!/bin/bash
# spec/sft-pilot.md. On the lab A100: smoke test, its stop rules, then one LoRA run (train, then score dev and eval
# with the adapter off and on) in one model load. Whole chain under a hard wall-clock cap (CAP_HOURS, default 3).
# Log ends with ALL_DONE, SMOKE_STOP <reason> or RUN_FAILED <rc>. Start (needs the user's OK each time):
#   cd <workdir>/gemma4-paper-track/sft && nohup bash sft_pilot_chain.sh > logs/chain.log 2>&1 &
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HUB_OFFLINE=1
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:${LD_LIBRARY_PATH:-}
cd <workdir>/gemma4-paper-track/sft
P=../.venv-sft/bin/python
M=../models/gemma-4-31B-it-qat-w4a16-ct
OUT=${OUT:-run1}
CAP_HOURS=${CAP_HOURS:-3}   # may be fractional (3.5)
TRAIN=${TRAIN:-train.jsonl} # training file inside data/ (addendum 1: train_pool.jsonl)
START=$(date +%s); DEADLINE=$((START + $(awk -v h="$CAP_HOURS" 'BEGIN{printf "%d", h * 3600}')))
left() { echo $((DEADLINE - $(date +%s))); }
echo "START $(date -u +%FT%TZ) out=$OUT cap=${CAP_HOURS}h train=$TRAIN"
[ -e "$OUT/run.json" ] && { echo "SMOKE_STOP $OUT/run.json exists (use a new OUT)"; exit 1; }

used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
[ "$used" -gt 2000 ] && { echo "SMOKE_STOP gpu_busy ${used}MiB"; exit 1; }

timeout "$(left)" $P sft_pilot.py smoke --model $M --data data --train "$TRAIN" --out "$OUT/smoke"
rc=$?; [ $rc -ne 0 ] && { echo "SMOKE_STOP smoke_failed rc=$rc $(date -u +%FT%TZ)"; exit 1; }

# stop rules fixed in the spec: memory, finite numbers, answer format, projected time within the cap
verdict=$($P - "$OUT/smoke/smoke.json" "$START" "$CAP_HOURS" <<'EOF'
import json, sys, time
s = json.load(open(sys.argv[1])); start, cap = int(sys.argv[2]), float(sys.argv[3])
elapsed = (time.time() - start) / 3600
bad = []
if s["max_mem_gb"] is None or s["max_mem_gb"] > 76: bad.append(f"memory {s['max_mem_gb']}GB")
if not (s["finite_scores"] and s["train_loss_finite"]): bad.append("non-finite")
if s["format_ok_off"] < 6: bad.append(f"format {s['format_ok_off']}/8")
if elapsed + s["projected_run_hours"] > 0.9 * cap: bad.append(f"time {elapsed:.2f}+{s['projected_run_hours']}h")
print("OK" if not bad else "STOP " + ";".join(bad))
EOF
)
echo "SMOKE_CHECK $verdict $(date -u +%FT%TZ)"
[ "$verdict" != "OK" ] && { echo "SMOKE_STOP $verdict"; exit 1; }

timeout "$(left)" $P sft_pilot.py run --model $M --data data --train "$TRAIN" --out "$OUT"
rc=$?; [ $rc -ne 0 ] && { echo "RUN_FAILED rc=$rc $(date -u +%FT%TZ)"; exit 1; }
echo "ALL_DONE $(date -u +%FT%TZ) elapsed_h=$(( ($(date +%s) - START) / 36 ))e-2"
