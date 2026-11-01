"""Gemma 4 31B's programs on LiveCodeBench release_v6 (spec/livecodebench-pilot.md).

Prompt and code extraction are lcb_runner's own for OpenAI-style chat models (LMStyle.OpenAIChat). One program per
problem, temperature 0, lcb_runner's default 2,000-token output limit, thinking off. Appends one JSON line per problem
to --out and skips problems already there, so a rerun resumes.

    python lcb_generate.py --out gemma4-31b.jsonl [--workers 16] [--limit N]
    python lcb_generate.py --out gemma4-31b.jsonl --export gemma4-31b.json   # custom-evaluator input

Rerun of the answers cut off at the output limit (spec addendum of 2026-11-01): --redo-from names the first run's file,
and only its rows with finish_reason "length" are generated again, with --max-tokens 8000. --merge at export replaces
those rows with the rerun's.

    python lcb_generate.py --out gemma4-31b-8k.jsonl --redo-from gemma4-31b.jsonl --max-tokens 8000
    python lcb_generate.py --out gemma4-31b.jsonl --merge gemma4-31b-8k.jsonl --export gemma4-31b-merged.json
"""
import argparse
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
from lcb_runner.lm_styles import LMStyle
from lcb_runner.prompts import format_prompt_generation
from lcb_runner.utils.extraction_utils import extract_code

URL = "http://127.0.0.1:18000/v1/chat/completions"
MODEL = "gemma4-qat"
MAX_TOKENS = 2000


def call(messages, max_tokens=MAX_TOKENS):
    body = {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.load(r)
    c = d["choices"][0]
    return c["message"]["content"] or "", c.get("finish_reason"), d.get("usage", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--export")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--redo-from")
    ap.add_argument("--merge")
    a = ap.parse_args()

    problems = sorted(load_code_generation_dataset("release_v6"), key=lambda p: str(p.question_id))
    done = {}
    if os.path.exists(a.out):
        for line in open(a.out):
            r = json.loads(line)
            done[r["question_id"]] = r

    if a.export:
        if a.merge:
            redo = {json.loads(l)["question_id"]: json.loads(l) for l in open(a.merge)}
            print(f"replacing {len(redo)} rows with the rerun's")
            done.update(redo)
        missing = [p.question_id for p in problems if p.question_id not in done]
        assert not missing, f"{len(missing)} problems have no program, e.g. {missing[:5]}"
        out = [{"question_id": p.question_id, "code_list": [done[p.question_id]["code"]]} for p in problems]
        json.dump(out, open(a.export, "w"))
        print(f"exported {len(out)} programs to {a.export}")
        return

    todo = [p for p in problems if p.question_id not in done]
    if a.redo_from:
        cut = {json.loads(l)["question_id"] for l in open(a.redo_from) if json.loads(l)["finish_reason"] == "length"}
        todo = [p for p in todo if p.question_id in cut]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(problems)} problems, {len(done)} done, {len(todo)} to generate", flush=True)

    def one(p):
        messages = format_prompt_generation(p, LMStyle.OpenAIChat)
        text, finish, usage = call(messages, a.max_tokens)
        return {"question_id": p.question_id, "difficulty": p.difficulty.value, "platform": p.platform.value,
                "contest_date": p.contest_date.isoformat(), "output": text, "code": extract_code(text, LMStyle.OpenAIChat),
                "finish_reason": finish, "usage": usage, "max_tokens": a.max_tokens}

    with open(a.out, "a") as f, ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(one, p) for p in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            f.write(json.dumps(fut.result()) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"{i}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
