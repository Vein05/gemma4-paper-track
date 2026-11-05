#!/bin/bash
# spec/base-vs-instruct.md. Waits for both downloads, runs the 40-patch format pilot for the pretrained, the bf16
# instruction-tuned and the 4-bit instruction-tuned model, checks the pilot rule (median digit probability >= 0.5 for
# every model), and only then scores all 957 patches with each model. Writes PILOT_FAIL or ALL_DONE to the log.
cd <workdir>/gemma4-paper-track/probe
P=../.venv-probe/bin/python
M=<workdir>/gemma4-paper-track/models
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
until grep -q "done google/gemma-4-31B-it" ../logs/download_base_vs_it.log 2>/dev/null; do sleep 60; done
declare -A DIR=([bvi_pre]=$M/gemma-4-31B [bvi_it]=$M/gemma-4-31B-it [bvi_q4]=$M/gemma-4-31B-it-qat-w4a16-ct)
for o in bvi_pre bvi_it bvi_q4; do
  echo "pilot $o $(date)"
  $P probe_extract.py plain --pilot-only --model ${DIR[$o]} --prompts base_vs_instruct_plain.jsonl --out $o || { echo "PILOT_ERROR $o"; exit 1; }
done
$P - <<'EOF' || { echo "PILOT_FAIL $(date)"; exit 1; }
import json, statistics, sys
ok = True
for o in ("bvi_pre", "bvi_it", "bvi_q4"):
    R = [json.loads(l) for l in open(f"{o}/plain.jsonl") if "logp100" in l]
    m = statistics.median(sum(r["p_digit"]) for r in R)
    print(o, len(R), "median p_digit", round(m, 3), flush=True)
    ok &= m >= 0.5
sys.exit(0 if ok else 1)
EOF
echo "PILOT_PASS $(date)"
for o in bvi_pre bvi_it bvi_q4; do
  echo "main $o $(date)"
  $P probe_extract.py plain --model ${DIR[$o]} --prompts base_vs_instruct_plain.jsonl --out $o || { echo "MAIN_ERROR $o"; exit 1; }
done
echo "ALL_DONE $(date)"
