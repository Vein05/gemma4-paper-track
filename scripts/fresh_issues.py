#!/usr/bin/env python3
"""Fresh-issue pool and sample for spec/fresh-replication.md.

  fetch: download patch.diff and report.json of the five control entries for every SWE-bench Verified issue outside
         the Mini 50 (public swe-bench-submissions bucket) -> data/public/swe-bench-verified-control-fresh/attempts.jsonl
  sample: pool = issues with at least one usable control patch (non-empty after removing test files, at most 30,000
          characters, with a label), as in the original study; pilot = 5 issues drawn with seed 1; the rest in a fixed random order (seed 0), so
          the first N of that order is the sample for any N -> .../sample.json
"""
import argparse, concurrent.futures as cf, json, os, sys, urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from api_quickcheck import strip_tests  # noqa: E402

OUT = os.path.join(HERE, "..", "data", "public", "swe-bench-verified-control-fresh")
MINI = os.path.join(HERE, "..", "data", "public", "gemma4-own-attempts", "swe-bench-verified-mini.parquet")
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com/bash-only"
ENTRIES = ["20250802_mini-v1.0.0_qwen3-coder-480b-a35b-instruct", "20250807_mini-v1.7.0_gpt-oss-120b",
           "20250822_mini-v1.9.1_glm-4.5", "20250807_mini-v1.7.0_kimi-k2-instruct",
           "20250720_mini-v0.0.0-Llama-4-Maverick-17B-Instruct"]
MAX_CHARS = 30000


def get(url):
    for _ in range(3):
        try:
            return urllib.request.urlopen(url, timeout=60).read().decode()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
    return None


def fetch(_):
    import pyarrow.parquet as pq
    from datasets import load_dataset
    mini = set(pq.read_table(MINI, columns=["instance_id"]).column("instance_id").to_pylist())
    iids = sorted(r["instance_id"] for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
                  if r["instance_id"] not in mini)

    def one(job):
        e, iid = job
        patch, rep = get(f"{BUCKET}/{e}/logs/{iid}/patch.diff"), get(f"{BUCKET}/{e}/logs/{iid}/report.json")
        r = json.loads(rep) if rep else {}
        res = r.get(iid, r).get("resolved")  # most reports are keyed by issue id; GLM-4.5's are not
        return dict(writer=e, instance_id=iid, patch=patch, resolved=res)

    os.makedirs(OUT, exist_ok=True)
    with cf.ThreadPoolExecutor(32) as pool, open(os.path.join(OUT, "attempts.jsonl"), "w") as f:
        for r in pool.map(one, [(e, i) for e in ENTRIES for i in iids]):
            f.write(json.dumps(r) + "\n")
    print(len(iids), "issues x", len(ENTRIES), "entries")


def sample(_):
    usable = {}
    for l in open(os.path.join(OUT, "attempts.jsonl")):
        a = json.loads(l)
        p = strip_tests(a["patch"] or "")
        ok = bool(p) and len(p) <= MAX_CHARS and a["resolved"] is not None
        usable.setdefault(a["instance_id"], []).append(ok)
    pool = sorted(i for i, v in usable.items() if any(v))
    pilot = sorted(np.random.default_rng(1).choice(pool, 5, replace=False).tolist())
    rest = [i for i in pool if i not in pilot]
    order = [rest[k] for k in np.random.default_rng(0).permutation(len(rest))]
    json.dump(dict(pool_size=len(pool), issues_checked=len(usable), pilot=pilot, order=order),
              open(os.path.join(OUT, "sample.json"), "w"), indent=1)
    print("pool", len(pool), "of", len(usable), "pilot", pilot)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "sample"])
    a = ap.parse_args()
    {"fetch": fetch, "sample": sample}[a.cmd](a)
