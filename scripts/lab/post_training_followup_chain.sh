#!/bin/bash
# spec/post-training-familiarity.md. Familiarity runs for the pretrained and bf16 instruction-tuned Gemma 4 31B (all
# 957 plain-text prompts), then waits for the OLMo 3 downloads, runs the 40-prompt format pilot for both OLMo models
# (median probability of a digit-led next token >= 0.5), and only then scores all 957 with each. Writes OLMO_PILOT_FAIL,
# MAIN_ERROR or ALL_DONE to the log.
cd <workdir>/gemma4-paper-track/probe
P=../.venv-probe/bin/python
M=<workdir>/gemma4-paper-track/models
X=base_vs_instruct_plain.jsonl
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
for o in gpre:gemma-4-31B git:gemma-4-31B-it; do
  echo "main fam_${o%%:*} $(date)"
  $P probe_extract.py fam --model $M/${o#*:} --prompts $X --out fam_${o%%:*} || { echo "MAIN_ERROR ${o%%:*}"; exit 1; }
done
until grep -q "done allenai/Olmo-3.1-32B-Instruct" ../logs/download_olmo.log 2>/dev/null; do sleep 60; done
for o in opre:olmo-3-32B oit:olmo-3.1-32B-Instruct; do
  echo "pilot fam_${o%%:*} $(date)"
  $P probe_extract.py fam --pilot-only --model $M/${o#*:} --prompts $X --out fam_${o%%:*} || { echo "PILOT_ERROR ${o%%:*}"; exit 1; }
done
$P - <<'EOF' || { echo "OLMO_PILOT_FAIL $(date)"; exit 1; }
import json, statistics, sys
ok = True
for o in ("fam_opre", "fam_oit"):
    R = [json.loads(l) for l in open(f"{o}/fam.jsonl") if "p_num" in l]
    m = statistics.median(r["p_num"] for r in R)
    print(o, len(R), "median p_num", round(m, 3), "space_moved", sum(r["space_moved"] for r in R), flush=True)
    ok &= m >= 0.5
sys.exit(0 if ok else 1)
EOF
echo "OLMO_PILOT_PASS $(date)"
for o in opre:olmo-3-32B oit:olmo-3.1-32B-Instruct; do
  echo "main fam_${o%%:*} $(date)"
  $P probe_extract.py fam --model $M/${o#*:} --prompts $X --out fam_${o%%:*} || { echo "MAIN_ERROR ${o%%:*}"; exit 1; }
done
echo "ALL_DONE $(date)"
