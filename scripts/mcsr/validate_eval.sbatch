#!/bin/bash
#SBATCH -J vein05-validate
#SBATCH -p cpuq
#SBATCH -c 12
#SBATCH --mem 64g
#SBATCH -t 08:00:00
#SBATCH -o logs/%x-%j.out
# Check (b) of spec/fresh-replication.md on Magnolia: re-grade 30 control patches with known official labels, no fakeroot.
set -euo pipefail
cd ~/vein05
export HF_HOME=$PWD/hf HF_HUB_OFFLINE=1 TMPDIR=$PWD/tmp WORK=$PWD/work/val-$SLURM_JOB_ID
export APPTAINER_CACHEDIR=$PWD/apptainer/cache APPTAINER_TMPDIR=$PWD/apptainer/tmp
export APPTAINER_EXEC_FLAGS="" APPTAINER_MOUNT_DIRS=/ddnlus
mkdir -p $TMPDIR $WORK runs/validate
trap 'rm -rf "$WORK"' EXIT
source venv/bin/activate
python scripts/eval_apptainer.py validate --entry 20250807_mini-v1.7.0_gpt-oss-120b --n 30 --workers 6 \
  --out runs/validate/val_gpt-oss-120b.jsonl
