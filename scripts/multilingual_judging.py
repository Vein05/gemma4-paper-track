#!/usr/bin/env python3
"""Judging of the SWE-bench Multilingual patches (spec/multilingual-replication.md): the held-out run's prompt,
settings and parser (scripts/fresh_judging.py), one pinned provider per judge, on Gemma's patches and the control
writers' failing patches.

run: one reasoning-first rating per patch. Gemma's patches come from the lab run directories (data/lab-runs/<run>/
  preds.json, mini-SWE-agent's own format); control patches from data/public/swe-bench-multilingual/attempts.jsonl,
  failing ones only, on the same issues. Test files are removed with the pattern below; patches over MAX_CHARS are
  dropped. Rows: derived/ml_<tag>.jsonl (resumes; --redo-unparsed asks unparsed answers once more).

Usage:
  python3 multilingual_judging.py run --model google/gemma-4-31b-it --tag gemma4-31b --provider novita --runs ml-smoke
"""
import argparse, concurrent.futures, json, os, re, sys

import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(__file__))
from fresh_judging import pid_of  # noqa: E402
from live_data import MAX_CHARS  # noqa: E402
from selection_test import rating_prompt  # noqa: E402
from selfjudge_matrix import Q_P1, call, parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
RUNS = os.path.join(ROOT, "data", "lab-runs")
DATA = os.path.join(ROOT, "data", "public", "swe-bench-multilingual")
WRITERS = ("glm-5", "kimi-k2-5", "deepseek-3-2", "minimax-2-5")
# the Verified pattern (api_quickcheck.PROTECTED) extended to the nine languages
TEST_FILE = re.compile(r"(^|/)(tests?|testing|spec|__tests__|testdata)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$"
                       r"|\.(test|spec)\.[jt]sx?$|_spec\.rb$|Tests?\.java$|(^|/)conftest\.py$")


def strip_tests(patch):
    parts = re.split(r"(?m)^(?=diff --git )", patch or "")
    keep = [p for p in parts if p.strip() and not ((m := re.match(r"diff --git a/(\S+) b/", p)) and TEST_FILE.search(m.group(1)))]
    return "".join(keep).strip()


def label(a):
    """Official label: the test report, or the entry's per-instance details when the report is missing."""
    return a["resolved"] if a["resolved"] is not None else a["resolved_details"]


def patches(runs):
    """Gemma's non-empty patches in the run directories, and the control writers' failing patches on the same issues."""
    gem = {}
    for r in runs:
        gem |= {iid: p["model_patch"] for iid, p in json.load(open(os.path.join(RUNS, r, "preds.json"))).items()}
    issues = {r["instance_id"]: r["problem_statement"] for r in pq.read_table(
        os.path.join(DATA, "data", "test-00000-of-00001.parquet"), columns=["instance_id", "problem_statement"]).to_pylist()}
    out = {}

    def add(iid, writer, patch, y):
        p = strip_tests(patch)
        if p and len(p) <= MAX_CHARS:
            out.setdefault(pid_of(iid, writer, p), dict(iid=iid, writer=writer, patch=p, y=y, issue=issues[iid]))
    for iid, patch in gem.items():
        add(iid, "gemma-4-31b", patch, None)
    for l in open(os.path.join(DATA, "attempts.jsonl")):
        a = json.loads(l)
        if a["instance_id"] in gem and label(a) is False:
            add(a["instance_id"], next(w for w in WRITERS if a["writer"].endswith(w)), a["patch"], 0)
    return out


def run(a):
    P = patches(a.runs.split(","))
    out = os.path.join(HERE, "derived", f"ml_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    jobs = [(dict(cond="P1", iid=x["iid"], pid=pid, writer=x["writer"], model=a.model), rating_prompt(x["iid"], x, Q_P1))
            for pid, x in sorted(P.items()) if pid not in done][:a.limit]
    print(f"{a.model}: patches {len(P)}, new calls {len(jobs)}", flush=True)
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, a.model, pr, a.max_tokens, a.provider): meta for meta, pr in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); row["parsed"] = parse("P1", row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush()


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--model", required=True); r.add_argument("--tag", required=True)
    r.add_argument("--runs", required=True); r.add_argument("--workers", type=int, default=8)
    r.add_argument("--redo-unparsed", action="store_true"); r.add_argument("--max-tokens", type=int, default=3000)
    r.add_argument("--limit", type=int, help="test pass only: at most this many new calls")
    r.add_argument("--provider", help="OpenRouter provider slug, no fallback (spec: one provider per judge)")
    a = ap.parse_args()
    run(a)


if __name__ == "__main__":
    main()
