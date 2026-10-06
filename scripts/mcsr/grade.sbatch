#!/bin/bash
#SBATCH -J vein05-grade
#SBATCH -p cpuq
#SBATCH -c 16
#SBATCH --mem 64g
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%j.out
# Grade (or finish grading) a run's patches on a CPU node, so GPU jobs need not hold their GPU while grading.
#   sbatch --export=ALL,RUN=runs/main-a,WORKERS=4 grade.sbatch     (resumes: skips issues already in labels.jsonl)
set -euo pipefail
cd ~/vein05
RUN=${RUN:?RUN}; WORKERS=${WORKERS:-4}; PREDS=${PREDS:-$RUN/preds.jsonl}
export HF_HOME=$PWD/hf HF_HUB_OFFLINE=1 TMPDIR=$PWD/tmp WORK=$PWD/work/grade-$SLURM_JOB_ID
export APPTAINER_CACHEDIR=$PWD/apptainer/cache APPTAINER_TMPDIR=$PWD/apptainer/tmp
export APPTAINER_EXEC_FLAGS="" APPTAINER_MOUNT_DIRS=/ddnlus
mkdir -p $TMPDIR $WORK
trap 'rm -rf "$WORK"' EXIT
source venv/bin/activate
python scripts/eval_apptainer.py eval --preds "$PREDS" --out "$RUN/labels.jsonl" --workers "$WORKERS"
