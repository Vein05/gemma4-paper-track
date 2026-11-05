#!/bin/bash
# spec/pretrained-judge-fix.md. Scores the 1,458 SWE-bench Lite plain-text prompts with the pretrained and the bf16
# instruction-tuned Gemma 4 31B (log P("100") after "SCORE: "). Writes MAIN_ERROR or ALL_DONE to the log.
cd <workdir>/gemma4-paper-track/probe
P=../.venv-probe/bin/python
M=<workdir>/gemma4-paper-track/models
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export LD_LIBRARY_PATH=<workdir>/_cuda-compat-test/ext/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
for o in lite_pre:gemma-4-31B lite_it:gemma-4-31B-it; do
  echo "main ${o%%:*} $(date)"
  $P probe_extract.py plain --model $M/${o#*:} --prompts base_vs_instruct_lite_plain.jsonl --out ${o%%:*} || { echo "MAIN_ERROR ${o%%:*}"; exit 1; }
done
echo "ALL_DONE $(date)"
