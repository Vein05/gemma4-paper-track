#!/usr/bin/env python3
"""Gemma 4 31B judging its own LiveCodeBench programs against other models' programs (spec/livecodebench-judging.md).
Run and analyze are those of scripts/third_party_lite.py, with this file's program set, prompt and row-file prefix.

build: 146 problems where Gemma's program ran and failed, 146 passing problems drawn within difficulty (seed 0);
  Gemma's program and the first released program of three other models on each, comments and docstrings removed
  -> data/livecodebench-pilot/judging/programs.jsonl
run / analyze: as in third_party_lite.py (row files scripts/derived/lcb_<tag>.jsonl).

Usage:
  python3 lcb_judging.py build
  python3 lcb_judging.py run --model google/gemma-4-31b-it --tag gemma4-31b --budget 0.3
  python3 lcb_judging.py analyze --judges gemma4-31b,... > scripts/derived/lcb_judging_<date>.json
"""
import ast, collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(__file__))
import selfjudge_matrix  # noqa: E402
import third_party_lite as T  # noqa: E402
from fresh_judging import pid_of  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PILOT = os.path.join(ROOT, "data", "livecodebench-pilot")
SUBS = os.path.join(ROOT, "data", "public", "livecodebench-submissions")
OUT = os.path.join(PILOT, "judging", "programs.jsonl")
GEMMA = "gemma-4-31b"
# GPT-4o (2024-08-06) was planned as a third writer and dropped for cost before judging (spec change, 2026-11-01)
OTHERS = {"DeepSeek-V3": ("deepseek-v3", None), "Claude-3.5-Sonnet-20241022": ("claude-3.5-sonnet", None)}
SYSTEM = ("You are an expert competitive programmer. You review a program written for a programming problem. "
          "You cannot run code; judge from the material given.")
Q = ("Question: will this program pass all of the problem's hidden tests, with correct output within the time and "
     "memory limits?\nExplain briefly, then end your reply with a final line that is exactly SCORE: <n>, where n is "
     "your probability from 0 to 100 that the hidden tests pass.")


def prompt(x):
    return (f"Below is a programming problem from {x['platform']}.\n\n<problem>\n{x['issue']}\n</problem>\n\n"
            f"A model wrote the Python program below for it.\n\n<program>\n{x['patch']}\n</program>\n\n" + Q)


def strip(code):
    """Remove comments and docstrings; keep the program as written if it does not parse."""
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


def build(_):
    E = {e["question_id"]: e for e in json.load(open(os.path.join(PILOT, "gemma4-31b-merged_codegeneration_output_eval_all.json")))}
    cut = {r["question_id"] for r in map(json.loads, open(os.path.join(PILOT, "gemma4-31b-8k.jsonl"))) if r["finish_reason"] == "length"}
    ids = sorted(E, key=str)
    fail = [q for q in ids if not E[q]["graded_list"][0] and q not in cut and E[q]["code_list"][0]]
    assert len(fail) == 146
    need = collections.Counter(E[q]["difficulty"] for q in fail)
    random.seed(0)
    passing = []
    for d in sorted(need):
        pool = [q for q in ids if E[q]["graded_list"][0] and E[q]["difficulty"] == d]
        passing += random.sample(pool, need[d])
    probs = fail + passing
    rows, counts = [], collections.Counter()

    def add(q, writer, code, y):
        if not code or not code.strip():
            counts[writer, "empty"] += 1
            return
        p, parsed = strip(code)
        counts[writer, "parsed" if parsed else "unparsed"] += 1
        e = E[q]
        rows.append(dict(pid=pid_of(q, writer, p), iid=q, writer=writer, patch=p, y=int(y), platform=e["platform"],
                         difficulty=e["difficulty"], issue=e["question_content"] + (
                             f"\n\nStarter code:\n{e['starter_code']}" if e["starter_code"] else "")))

    for q in probs:
        add(q, GEMMA, E[q]["code_list"][0], E[q]["graded_list"][0])
    for f, (writer, _) in OTHERS.items():
        R = {r["question_id"]: r for r in json.load(open(os.path.join(SUBS, f + ".json")))}
        for q in probs:
            r = R.get(q)
            if r and r["code_list"]:
                add(q, writer, r["code_list"][0], r["graded_list"][0])
            else:
                counts[writer, "missing"] += 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    lab = collections.defaultdict(collections.Counter)
    for r in rows:
        lab[r["writer"]]["pass" if r["y"] else "fail"] += 1
    print(json.dumps(dict(problems=len(probs), counts={f"{w}:{k}": v for (w, k), v in counts.items()},
                          labels={w: dict(c) for w, c in lab.items()}), indent=1))


def setup():
    T.PATCHES, T.PREFIX, T.PROMPT, T.GEMMA = OUT, "lcb", prompt, GEMMA
    T.WRITER_FAMILY = {GEMMA: "gemma", **{w: f for w, f in OTHERS.values()}}
    selfjudge_matrix.SYSTEM = SYSTEM


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build(None)
    else:
        setup()
        T.main()
