#!/bin/bash
# BigCodeBench-Hard pilot on the lab server (spec/bigcodebench-pilot.md). Runs BigCodeBench's own code inside its
# evaluation image (a local Apptainer file), with only the work folder visible to it.
#   bash bcb_pilot.sh gt          reference solutions of the 148 tasks
#   bash bcb_pilot.sh validate    regrade DeepSeek-V3's released Hard instruct programs (published: 28.4%)
#   bash bcb_pilot.sh generate    Gemma's programs from the vLLM server on port 18000 (4 shards at once)
#   bash bcb_pilot.sh grade       grade Gemma's programs
# Full set, complete split (spec/bigcodebench-full.md):
#   bash bcb_pilot.sh full-validate   regrade DeepSeek-V3's released full complete programs (published: 62.2%)
#   bash bcb_pilot.sh full-generate   Gemma's programs on all 1,140 tasks (8 shards at once)
#   bash bcb_pilot.sh full-grade      grade them
B=<workdir>/gemma4-paper-track/bcb
A=<workdir>/swe-env/apptainer/bin/apptainer
SIF=$B/bigcodebench-evaluate.sif
W=$B/work
mkdir -p $W/tmp $W/cache
run() {
  # /tmp on disk: --contain would give a small in-memory /tmp; the dataset cache goes to the work folder
  $A exec --contain --cleanenv --env OPENAI_API_KEY=none --env XDG_CACHE_HOME=/work/cache -B $W:/work -B $W/tmp:/tmp \
    --pwd /work $SIF "$@"
}
EVAL="python3 -m bigcodebench.evaluate --split instruct --subset hard --execution local --parallel 16"
FULL="python3 -m bigcodebench.evaluate --split complete --subset full --execution local --parallel 16"
case "$1" in
  gt) run $EVAL --check_gt_only ;;
  validate) run $EVAL --samples /work/released/deepseek-v3-hard-instruct.jsonl ;;
  generate)
    for r in 0-37 37-74 74-111 111-148; do
      run python3 -m bigcodebench.generate --model gemma4-qat --backend openai --base_url http://127.0.0.1:18000/v1 \
        --split instruct --subset hard --greedy --id_range $r --root /work/gen-$r > $B/logs/generate-$r.log 2>&1 &
    done
    wait
    cat $W/gen-*/gemma4-qat--main--bigcodebench-hard-instruct--openai-0-1-sanitized_calibrated.jsonl \
      > $W/gemma4-31b-hard-instruct.jsonl
    wc -l $W/gemma4-31b-hard-instruct.jsonl ;;
  grade) run $EVAL --samples /work/gemma4-31b-hard-instruct.jsonl ;;
  full-validate) run $FULL --samples /work/released/deepseek-v3-full-complete.jsonl ;;
  full-generate)
    # load the dataset once: two pilot shards that started together raced on its download
    run python3 -c "from bigcodebench.data import get_bigcodebench; print(len(get_bigcodebench(subset='full')))"
    mkdir -p $W/full
    for r in 0-143 143-286 286-429 429-572 572-715 715-858 858-1001 1001-1140; do
      run python3 -m bigcodebench.generate --model gemma4-qat --backend openai --base_url http://127.0.0.1:18000/v1 \
        --split complete --subset full --greedy --id_range $r --root /work/full/gen-$r \
        > $B/logs/full-generate-$r.log 2>&1 &
    done
    wait
    cat $W/full/gen-*/*sanitized_calibrated.jsonl > $W/gemma4-31b-full-complete.jsonl
    wc -l $W/gemma4-31b-full-complete.jsonl ;;
  full-grade) run $FULL --samples /work/gemma4-31b-full-complete.jsonl ;;
  *) echo "usage: bcb_pilot.sh gt|validate|generate|grade|full-validate|full-generate|full-grade"; exit 1 ;;
esac
