#!/bin/bash
# LiveCodeBench pilot on the lab server (spec/livecodebench-pilot.md). Runs LiveCodeBench's own code (lcb_runner) in a
# Python 3.11 Apptainer container that sees only the lcb folder.
#   bash lcb_pilot.sh setup      pull the container, make the venv, download release_v6 (1,055 problems)
#   bash lcb_pilot.sh validate   regrade DeepSeek-V3's released programs (first of ten per problem; released: 49.8%)
#   bash lcb_pilot.sh generate   Gemma's programs from the vLLM server on port 18000
#   bash lcb_pilot.sh grade      grade Gemma's programs
#   bash lcb_pilot.sh redo       regenerate the answers cut off at 2,000 tokens with an 8,000-token limit
#   bash lcb_pilot.sh grade8k    grade Gemma's programs with the rerun's answers in place of the cut-off ones
L=<workdir>/gemma4-paper-track/lcb
A=<workdir>/swe-env/apptainer/bin/apptainer
SIF=$L/python311.sif
W=$L/work
mkdir -p $W/tmp $L/logs
run() {
  $A exec --contain --cleanenv --env HF_HOME=/lcb/hf --env PYTHONNOUSERSITE=1 -B $L:/lcb -B $W/tmp:/tmp --pwd /lcb/LiveCodeBench \
    $SIF "$@"
}
PY=/lcb/venv/bin/python
EVAL="$PY -m lcb_runner.runner.custom_evaluator --scenario codegeneration --release_version release_v6
  --num_process_evaluate 16 --timeout 6"
case "$1" in
  setup)
    [ -f $SIF ] || $A pull $SIF docker://python:3.11-slim
    run python -m venv /lcb/venv
    run $PY -m pip install -q "datasets==3.6.0" numpy tqdm pebble
    run $PY -m pip install -q --no-deps -e /lcb/LiveCodeBench
    run $PY -c "
from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
d = load_code_generation_dataset('release_v6')
print(len(d), min(p.contest_date for p in d), max(p.contest_date for p in d))" ;;
  validate)
    run $PY /lcb/scripts/lcb_released.py /lcb/released/deepseek-v3.json /lcb/work/deepseek-v3-first.json
    run $EVAL --custom_output_file /lcb/work/deepseek-v3-first.json ;;
  generate)
    run $PY /lcb/scripts/lcb_generate.py --out /lcb/work/gemma4-31b.jsonl --workers 16 ;;
  grade)
    run $PY /lcb/scripts/lcb_generate.py --out /lcb/work/gemma4-31b.jsonl --export /lcb/work/gemma4-31b.json
    run $EVAL --custom_output_file /lcb/work/gemma4-31b.json ;;
  redo)
    run $PY /lcb/scripts/lcb_generate.py --out /lcb/work/gemma4-31b-8k.jsonl --redo-from /lcb/work/gemma4-31b.jsonl \
      --max-tokens 8000 --workers 16 ;;
  grade8k)
    run $PY /lcb/scripts/lcb_generate.py --out /lcb/work/gemma4-31b.jsonl --merge /lcb/work/gemma4-31b-8k.jsonl \
      --export /lcb/work/gemma4-31b-merged.json
    run $EVAL --custom_output_file /lcb/work/gemma4-31b-merged.json ;;
  *) echo "usage: lcb_pilot.sh setup|validate|generate|grade|redo|grade8k"; exit 1 ;;
esac
