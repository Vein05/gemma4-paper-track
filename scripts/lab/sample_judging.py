#!/usr/bin/env python3
"""Addendum 8 of spec/judge-probe.md: n samples per judging prompt at temperature 1.0 from a vLLM server.
Standard library only. Usage: python3 sample_judging.py --base URL --model NAME --prompts FILE --out FILE [--n 8]"""
import argparse, concurrent.futures, json, os, re, urllib.request


def parse(c):
    m = re.findall(r"SCORE:\s*\**\s*(\d{1,3})", c or "")
    return min(100, int(m[-1])) if m else None


def one(a, r):
    body = {"model": a.model, "messages": [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["prompt"]}],
            "temperature": 1.0, "top_p": 1.0, "n": a.n, "max_tokens": a.max_tokens, "seed": 0}
    req = urllib.request.Request(a.base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req, timeout=3600))
    scores = [parse(ch["message"].get("content")) for ch in out["choices"]]
    return {"pid": r["pid"], "scores": scores}


def main():
    ap = argparse.ArgumentParser()
    for k, d in (("--base", None), ("--model", None), ("--prompts", None), ("--out", None)):
        ap.add_argument(k, required=True)
    ap.add_argument("--n", type=int, default=8); ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    done = {json.loads(l)["pid"] for l in open(a.out)} if os.path.exists(a.out) else set()
    rows = [json.loads(l) for l in open(a.prompts)]
    rows = [r for r in rows if r["pid"] not in done]
    with open(a.out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        for i, f in enumerate(concurrent.futures.as_completed([ex.submit(one, a, r) for r in rows])):
            try:
                fh.write(json.dumps(f.result()) + "\n"); fh.flush()
            except Exception as e:
                print("error", type(e).__name__, str(e)[:200], flush=True)
            if i % 50 == 0:
                print(i, "done", flush=True)
    print("SAMPLING_FINISHED", flush=True)


if __name__ == "__main__":
    main()
