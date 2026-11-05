#!/bin/bash
# Reference patches of all 300 SWE-bench Multilingual issues graded on the lab server's CPUs: an issue is kept only if
# its reference patch passes (spec/multilingual-replication.md). From ml/ on the server:
#   (cd <workdir>/gemma4-paper-track/ml; nohup bash gold_multilingual.sh > logs/ml_gold.log 2>&1 &)
# Resumes: graded issues are skipped.
cd <workdir>/gemma4-paper-track/ml || exit 1
. ./env.sh
PY=<workdir>/swe-env/venv20/bin/python
OUT=runs/ml-gold
DS=data/public/swe-bench-multilingual/data/test-00000-of-00001.parquet
mkdir -p $OUT
[ -s $OUT/preds.jsonl ] || $PY - $DS > $OUT/preds.jsonl <<'PY'
import json, sys
import pyarrow.parquet as pq
for r in pq.read_table(sys.argv[1], columns=["instance_id", "patch"]).to_pylist():
    print(json.dumps(dict(instance_id=r["instance_id"], model_patch=r["patch"])))
PY
echo "gold start $(date -Is), $(wc -l < $OUT/preds.jsonl) patches"
$PY scripts/eval_apptainer.py eval --dataset $DS --preds $OUT/preds.jsonl --out $OUT/labels.jsonl --workers 2
echo "gold end $(date -Is), exit $?"
