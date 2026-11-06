#!/usr/bin/env python3
"""Lab-side steps of spec/lcb-same-model.md, run in the LiveCodeBench container (CPU only, no key on the lab server).

  python lcb_same_model_lab.py dump --ids sweep_ids.json --out messages.jsonl    # LiveCodeBench's chat prompts
  python lcb_same_model_lab.py code --rows <writer>.jsonl                        # add lcb_runner's extracted code in place
"""
import argparse, json

from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
from lcb_runner.lm_styles import LMStyle
from lcb_runner.prompts import format_prompt_generation
from lcb_runner.utils.extraction_utils import extract_code

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["dump", "code"])
ap.add_argument("--ids"); ap.add_argument("--out"); ap.add_argument("--rows")
a = ap.parse_args()
if a.cmd == "dump":
    keep = set(json.load(open(a.ids)))
    probs = sorted(load_code_generation_dataset("release_v6"), key=lambda p: str(p.question_id))
    with open(a.out, "w") as f:
        for p in probs:
            if p.question_id in keep:
                f.write(json.dumps(dict(question_id=p.question_id, difficulty=p.difficulty.value, platform=p.platform.value,
                                        contest_date=p.contest_date.isoformat(),
                                        messages=format_prompt_generation(p, LMStyle.OpenAIChat))) + "\n")
else:
    rows = list(map(json.loads, open(a.rows)))
    for r in rows:
        r["code"] = extract_code(r["output"] or "", LMStyle.OpenAIChat)
    with open(a.rows, "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    print(a.rows, len(rows), "rows,", sum(bool(r["code"].strip()) for r in rows), "with code")
