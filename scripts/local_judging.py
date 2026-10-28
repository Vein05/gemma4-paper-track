#!/usr/bin/env python3
"""Held-out judging by other Gemma 4 sizes served locally with vLLM (spec/gemma-sizes-judges.md).

export: the exact held-out P1 prompts (fresh_judging.patches, selection_test.rating_prompt with Q_P1, system message of
  selfjudge_matrix.call) for every patch the 31B judge scored. Needs the repo's Python environment; run it on the Mac.
run: POST each prompt to a vLLM OpenAI-compatible server at temperature 0. Standard library only, so it runs on the lab
  server. Resumes like fresh_judging.run (--redo-unparsed asks unparsed answers once more, e.g. with --max-tokens 8000).
  Rows: derived/fresh_<tag>.jsonl, the fields of the OpenRouter judges' rows plus reasoning_tokens, reasoning_chars, seconds.

Usage:
  python3 local_judging.py export [--out ../data/judge-prompts/heldout_p1.jsonl]
  python3 local_judging.py run --base http://127.0.0.1:18001/v1 --model gemma4-12b --tag gemma4-12b \
      --prompts heldout_p1.jsonl --out derived/fresh_gemma4-12b.jsonl [--smoke] [--workers 8] [--max-tokens 3000]
"""
import argparse, collections, concurrent.futures, json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def parse_p1(content):
    """Copy of selfjudge_matrix.parse("P1", ...), which cannot be imported here (its imports are not standard library)."""
    if content is None:
        return None
    m = re.findall(r"SCORE:\s*\**\s*(\d{1,3})", content)
    return min(100, int(m[-1])) if m else None


def export(a):
    sys.path.insert(0, HERE)
    from fresh_judging import patches
    from selection_test import rating_prompt
    from selfjudge_matrix import Q_P1, SYSTEM
    P = patches(["main-a", "main-b", "mini50"])  # the runs of fresh_gemma4-31b.jsonl (changelog/2026-10-06.md)
    pids = sorted({json.loads(l)["pid"] for l in open(os.path.join(HERE, "derived", "fresh_gemma4-31b.jsonl"))})
    missing = [p for p in pids if p not in P]
    assert not missing, f"{len(missing)} pids not found, e.g. {missing[:3]}"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        for p in pids:
            x = P[p]
            fh.write(json.dumps(dict(pid=p, iid=x["iid"], writer=x["writer"], system=SYSTEM,
                                     prompt=rating_prompt(x["iid"], x, Q_P1))) + "\n")
    print(f"{len(pids)} prompts to {a.out}", dict(collections.Counter(P[p]["writer"] for p in pids)))


def call(base, model, system, prompt, max_tokens, retries=4):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": max_tokens}
    err = None
    for k in range(retries):
        req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            r = json.load(urllib.request.urlopen(req, timeout=1200))
            msg = r["choices"][0]["message"]
            u = r.get("usage") or {}
            return dict(content=(msg.get("content") or "").strip(), provider="local-vllm",
                        prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"), cost=0,
                        reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                        reasoning_chars=len(msg.get("reasoning_content") or msg.get("reasoning") or ""),
                        seconds=round(time.time() - t0, 1), err=None)
        except Exception as e:
            err = f"{type(e).__name__}: {getattr(e, 'code', '')} {str(e)[:200]}"
            time.sleep(2 * (k + 1))
    return dict(content=None, err=err)


def run(a):
    rows = sorted((json.loads(l) for l in open(a.prompts)), key=lambda r: r["pid"])
    if a.smoke:
        own = [r for r in rows if r["writer"] == "gemma-4-31b"][:10]
        rows = own + [r for r in rows if r["writer"] != "gemma-4-31b"][:10]
    out = a.out or os.path.join(HERE, "derived", f"fresh_{a.tag}.jsonl")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    jobs = [r for r in rows if r["pid"] not in done]
    print(f"{a.model}: prompts {len(rows)}, new calls {len(jobs)}", flush=True)
    res = []
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, a.base, a.model, r["system"], r["prompt"], a.max_tokens):
                dict(cond="P1", iid=r["iid"], pid=r["pid"], writer=r["writer"], model=a.model) for r in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); row["parsed"] = parse_p1(row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush(); res.append(row)
    if a.smoke and res:
        ok = [r for r in res if r["err"] is None]
        print(f"smoke: calls {len(res)}, errors {len(res) - len(ok)}, parsed {sum(r['parsed'] is not None for r in ok)}, "
              f"with reasoning {sum(bool(r.get('reasoning_chars')) or bool(r.get('reasoning_tokens')) for r in ok)}, "
              f"mean seconds {sum(r['seconds'] for r in ok) / max(1, len(ok)):.1f}, "
              f"mean completion tokens {sum(r['completion_tokens'] or 0 for r in ok) / max(1, len(ok)):.0f}, "
              f"max prompt tokens {max((r['prompt_tokens'] or 0 for r in ok), default=0)}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("export"); e.add_argument("--out", default=os.path.join(ROOT, "data", "judge-prompts", "heldout_p1.jsonl"))
    r = sp.add_parser("run"); r.add_argument("--base", default="http://127.0.0.1:18001/v1")
    r.add_argument("--model", required=True, help="served model name"); r.add_argument("--tag", required=True)
    r.add_argument("--prompts", required=True); r.add_argument("--out", help="default derived/fresh_<tag>.jsonl")
    r.add_argument("--max-tokens", type=int, default=3000); r.add_argument("--workers", type=int, default=8)
    r.add_argument("--redo-unparsed", action="store_true")
    r.add_argument("--smoke", action="store_true", help="first 10 pids written by gemma-4-31b and first 10 by other writers")
    a = ap.parse_args()
    export(a) if a.cmd == "export" else run(a)


if __name__ == "__main__":
    main()
