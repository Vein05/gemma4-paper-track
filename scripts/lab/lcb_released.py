"""Turn a released LiveCodeBench submission file into the custom-evaluator input: the first program per problem.

    python lcb_released.py RELEASED.json OUT.json
"""
import json
import sys

rows = json.load(open(sys.argv[1]))
# DeepSeek-V3's file has no program for 30 problems (graded as fails there); an empty program keeps them as fails.
out = [{"question_id": r["question_id"], "code_list": [r["code_list"][0] if r["code_list"] else ""]} for r in rows]
json.dump(out, open(sys.argv[2], "w"))
first = sum(bool(r["graded_list"][0]) for r in rows)
empty = sum(not r["code_list"] for r in rows)
print(f"{len(out)} problems ({empty} without a program); released grade of the first program: {first} pass "
      f"({first / len(rows):.1%})")
