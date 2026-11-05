#!/usr/bin/env python3
"""Judging prompts for a sweep model's LiveCodeBench programs (spec/lcb-model-sweep.md). Standard library only, so it
runs on the lab server. Program cleaning (comments and docstrings removed), prompt and system message are copies of
scripts/lcb_judging.py (strip, prompt, SYSTEM, Q); pid as fresh_judging.pid_of.

Problem text and platform come from the existing prompts (lcb_p1.jsonl, already on the lab server).

  python3 lcb_sweep_prompts.py --existing lcb_p1.jsonl --gen <model>.jsonl --writer <name> --out <name>_p1.jsonl
  python3 lcb_sweep_prompts.py --existing lcb_p1.jsonl --check programs.jsonl   # on the Mac: parsed text == source
"""
import argparse, ast, hashlib, json, re

SYSTEM = ("You are an expert competitive programmer. You review a program written for a programming problem. "
          "You cannot run code; judge from the material given.")
Q = ("Question: will this program pass all of the problem's hidden tests, with correct output within the time and "
     "memory limits?\nExplain briefly, then end your reply with a final line that is exactly SCORE: <n>, where n is "
     "your probability from 0 to 100 that the hidden tests pass.")


def prompt(x):
    return (f"Below is a programming problem from {x['platform']}.\n\n<problem>\n{x['issue']}\n</problem>\n\n"
            f"A model wrote the Python program below for it.\n\n<program>\n{x['patch']}\n</program>\n\n" + Q)


def strip(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, False
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                n.body = n.body[1:] or [ast.Pass()]
    return ast.unparse(tree), True


def pid_of(iid, writer, patch):
    return f"{iid}|{writer}|{hashlib.md5(patch.encode()).hexdigest()[:8]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--existing", required=True); ap.add_argument("--gen"); ap.add_argument("--writer")
    ap.add_argument("--out"); ap.add_argument("--check")
    a = ap.parse_args()
    probs = {}
    for r in map(json.loads, open(a.existing)):
        m = re.match(r"Below is a programming problem from (.*?)\.\n\n<problem>\n(.*)\n</problem>\n\nA model wrote",
                     r["prompt"], re.S)
        probs.setdefault(r["iid"], dict(platform=m.group(1), issue=m.group(2)))
    if a.check:
        rows = list(map(json.loads, open(a.check)))
        same = sum(probs[r["iid"]]["platform"] == r["platform"] and probs[r["iid"]]["issue"] == r["issue"]
                   and prompt(dict(probs[r["iid"]], patch=r["patch"])) == prompt(r) for r in rows)
        print(f"problem text recovered for {same} of {len(rows)} programs")
        return
    n = dict(written=0, empty=0, unparsed=0)
    with open(a.out, "w") as f:
        for g in map(json.loads, open(a.gen)):
            q = g["question_id"]
            if q not in probs:
                continue
            if not (g.get("code") or "").strip():
                n["empty"] += 1
                continue
            p, ok = strip(g["code"])
            n["unparsed"] += not ok
            x = dict(probs[q], patch=p)
            f.write(json.dumps(dict(pid=pid_of(q, a.writer, p), iid=q, writer=a.writer, system=SYSTEM,
                                    prompt=prompt(x))) + "\n")
            n["written"] += 1
    print(a.writer, n)


if __name__ == "__main__":
    main()
