#!/usr/bin/env python3
"""Gemma 4 31B's SWE-bench Lite patches from another team's run, judged by the paper's nine judges
(spec/third-party-lite.md). Same prompt, settings, parser and measures as scripts/fresh_judging.py.

build: Gemma's patches and labels (data/public/third-party-lite/gemma, from scripts/lab/pull_third_party_lite.py) and
  four Lite leaderboard entries' patches and labels on the same issues -> data/public/third-party-lite/patches.jsonl
run: one rating per patch for one judge -> scripts/derived/lite_<tag>.jsonl (resumes; --redo-unparsed re-asks once)
analyze: rubber-stamp rates, patch-matched leniency and the self-judging gap, as in fresh_judging.py analyze.

Usage:
  python3 third_party_lite.py build
  python3 third_party_lite.py run --model google/gemma-4-31b-it --tag gemma4-31b [--workers 8] [--limit N]
  python3 third_party_lite.py analyze --judges gemma4-31b,... > scripts/derived/third_party_lite_<date>.json
"""
import argparse, collections, concurrent.futures, glob, json, os, sys, urllib.error, urllib.request

import numpy as np
from scipy.stats import rankdata

sys.path.insert(0, os.path.dirname(__file__))
from api_quickcheck import strip_tests  # noqa: E402
from fresh_judging import FAMILY, pid_of  # noqa: E402
from live_data import MAX_CHARS  # noqa: E402
from selection_test import rating_prompt  # noqa: E402
from selfjudge_matrix import Q_P1, call, parse  # noqa: E402
from self_judging_replication import auroc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "public", "third-party-lite")
PATCHES = os.path.join(DATA, "patches.jsonl")
GEMMA = "gemma-4-31b"
# Lite leaderboard entries used as other writers, and the judge family each writer belongs to (None: no judge of it)
CONTROLS = {"20250111_moatless_deepseek_v3": ("deepseek-v3", None),
            "20250306_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor": ("swe-fixer-qwen2.5-72b", "qwen"),
            "20250901_entroPO_R2E_QwenCoder30BA3B": ("entropo-qwen3-coder-30b", "qwen"),
            "20250526_sweagent_claude-4-sonnet-20250514": ("claude-4-sonnet", None)}
WRITER_FAMILY = {GEMMA: "gemma", **{w: f for w, f in CONTROLS.values()}}
PREFIX = "lite"  # row files scripts/derived/<PREFIX>_<tag>.jsonl; scripts/lcb_judging.py reuses run and analyze
PROMPT = lambda x: rating_prompt(x["iid"], x, Q_P1)
GH = "https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/lite"
S3 = "https://swe-bench-submissions.s3.amazonaws.com/lite"


def get(url):
    return urllib.request.urlopen(url, timeout=120).read().decode()


def build(_):
    from datasets import load_dataset
    res = json.load(open(os.path.join(DATA, "gemma", "results", "results.json")))
    lab = {i: int(t["resolved"]) for i, t in res["task_results"].items() if t["graded"]}
    issues = {r["instance_id"]: r["problem_statement"] for r in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")}
    rows, counts = [], collections.Counter()

    def add(iid, writer, patch, y, src):
        p = strip_tests(patch or "")
        if not p:
            counts[writer, "empty"] += 1
        elif len(p) > MAX_CHARS:
            counts[writer, "too_long"] += 1
        else:
            rows.append(dict(pid=pid_of(iid, writer, p), iid=iid, writer=writer, patch=p, y=y, issue=issues[iid], source=src))
            counts[writer, "used"] += 1

    for f in sorted(glob.glob(os.path.join(DATA, "gemma", "rollouts", "*", "*", "preds.json"))):
        for iid, p in json.load(open(f)).items():
            add(iid, GEMMA, p["model_patch"], lab[iid], os.path.relpath(f, DATA))
    for entry, (writer, _) in CONTROLS.items():
        done = set(json.loads(get(f"{GH}/{entry}/results/results.json"))["resolved"])
        try:
            preds = {p["instance_id"]: (p.get("model_patch"), f"{S3}/{entry}/all_preds.jsonl")
                     for p in map(json.loads, get(f"{S3}/{entry}/all_preds.jsonl").splitlines())}
        except urllib.error.HTTPError:  # no all_preds.jsonl: the per-issue patch files the evaluator used
            def one(iid):
                u = f"{S3}/{entry}/logs/{iid}/patch.diff"
                try:
                    return iid, (get(u), u)
                except urllib.error.HTTPError:
                    return iid, (None, u)
            with concurrent.futures.ThreadPoolExecutor(16) as ex:
                preds = dict(ex.map(one, sorted(lab)))
        for iid in sorted(lab):
            if iid in preds:
                add(iid, writer, preds[iid][0], int(iid in done), preds[iid][1])
            else:
                counts[writer, "missing"] += 1
    with open(PATCHES, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[r["writer"]]["fail" if r["y"] == 0 else "pass"] += 1
    print(json.dumps(dict(counts={f"{w}:{k}": v for (w, k), v in counts.items()}, labels={w: dict(c) for w, c in by.items()}),
                     indent=1))


def run(a):
    P = {r["pid"]: r for r in map(json.loads, open(PATCHES))}
    out = os.path.join(HERE, "derived", f"{PREFIX}_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    jobs = [(dict(cond="P1", iid=x["iid"], pid=pid, writer=x["writer"], model=a.model), PROMPT(x))
            for pid, x in sorted(P.items()) if pid not in done][:a.limit]
    print(f"{a.model}: patches {len(P)}, new calls {len(jobs)}", flush=True)
    spent = sum(r.get("cost") or 0 for r in map(json.loads, open(out))) if os.path.exists(out) else 0.0
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, a.model, pr, a.max_tokens): meta for meta, pr in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); row["parsed"] = parse("P1", row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush()
            spent += row.get("cost") or 0
            if a.budget and spent > a.budget:  # spending limit for this judge: cancel the calls not yet started
                print(f"budget ${a.budget} reached (${spent:.3f}); stopping", flush=True)
                for g in futs:
                    g.cancel()
                break


def analyze(a):
    judges = a.judges.split(",")
    P = {r["pid"]: r for r in map(json.loads, open(PATCHES))}
    S = collections.defaultdict(dict)
    for t in judges:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"{PREFIX}_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in S.items() if len(s) == len(judges))
    if a.leave_out_reasked:  # exploratory, as fresh_judging.py: items where any judge's first answer had no parsed score
        reasked = {r["pid"] for t in judges for r in map(json.loads, open(os.path.join(HERE, "derived", f"{PREFIX}_{t}.jsonl")))
                   if r.get("parsed") is None}
        pids = [p for p in pids if p not in reasked]
    y = np.array([P[p]["y"] for p in pids]); wr = np.array([P[p]["writer"] for p in pids])
    iss = np.array([P[p]["iid"] for p in pids])
    X = {t: np.array([S[p][t] for p in pids], float) for t in judges}
    j, w = "gemma4-31b", GEMMA
    outside = [k for k in judges if k != j]
    ks_of = [[k for k in outside if FAMILY[k] != WRITER_FAMILY[v]] for v in wr]  # outside judges per patch

    def measures(idx):
        own, rest = idx[wr[idx] == w], idx[wr[idx] != w]
        self_drop = auroc(X[j][rest], y[rest]) - auroc(X[j][own], y[own])
        drops = {}
        for k in outside:  # no outside judge wrote any of these patches, so each judge is scored on all other writers
            rk = rest[np.array([FAMILY[k] != WRITER_FAMILY[v] for v in wr[rest]], bool)]
            drops[k] = auroc(X[k][rk], y[rk]) - auroc(X[k][own], y[own])
        base = float(np.mean(list(drops.values())))
        return dict(gemma_auroc_own=auroc(X[j][own], y[own]), gemma_auroc_control=auroc(X[j][rest], y[rest]),
                    self_drop=self_drop, baseline_drop=base, gap=self_drop - base)

    R = {t: (rankdata(X[t]) - 1) / (len(pids) - 1) for t in judges}
    D = {name: np.array([Z[j][i] - np.mean([Z[k][i] for k in ks_of[i]]) for i in range(len(pids))])
         for name, Z in (("raw", X), ("rank", R))}

    def leniency(idx):
        out = {}
        for name, d in D.items():
            for lab_, yy in (("failing", 0), ("passing", 1)):
                sel = idx[y[idx] == yy]
                own, rest = d[sel[wr[sel] == w]], d[sel[wr[sel] != w]]
                out[f"lenient_{name}_{lab_}_own"] = own.mean()
                out[f"lenient_{name}_{lab_}_control"] = rest.mean()
                out[f"lenient_{name}_{lab_}_difference"] = own.mean() - rest.mean()
        return out

    def stamp(idx):
        f = idx[y[idx] == 0]
        own, rest = f[wr[f] == w], f[wr[f] != w]
        out = {"gemma_scored100_own_failing": (X[j][own] == 100).mean(),
               "gemma_scored100_control_failing": (X[j][rest] == 100).mean(),
               "outside_scored100_own_failing": np.mean([(X[k][own] == 100).mean() for k in outside])}
        out["gemma_scored100_own_minus_control_failing"] = out["gemma_scored100_own_failing"] - out["gemma_scored100_control_failing"]
        out["gemma_minus_outside_scored100_own_failing"] = out["gemma_scored100_own_failing"] - out["outside_scored100_own_failing"]
        return out

    allidx = np.arange(len(pids))
    point = measures(allidx) | leniency(allidx) | stamp(allidx)
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    BOOT = ["self_drop", "baseline_drop", "gap", "gemma_scored100_own_minus_control_failing",
            "gemma_minus_outside_scored100_own_failing"] + [f"lenient_{n}_{f}_difference" for n in D for f in ("failing", "passing")]
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        m = measures(idx) | leniency(idx) | stamp(idx)
        for k in BOOT:
            boot[k].append(m[k])
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    fail = y == 0
    res = {k: round(float(v), 3) for k, v in point.items()}
    res.update({f"{k}_ci95": ci(boot[k]) for k in BOOT})
    for t in judges:
        res[f"{t}_scored100_own_failing"] = round(float((X[t][fail & (wr == w)] == 100).mean()), 3)
        res[f"{t}_scored100_control_failing"] = round(float((X[t][fail & (wr != w)] == 100).mean()), 3)
        res[f"{t}_auroc_by_writer"] = {v: round(float(auroc(X[t][wr == v], y[wr == v])), 3) for v in sorted(set(wr))}
    res.update(judges=judges, outside_judges=outside, issues=len(issues), patches_rated_by_all=len(pids),
               patches_left_out=len(P) - len(pids),
               n=dict(own_failing=int((fail & (wr == w)).sum()), own_passing=int((~fail & (wr == w)).sum()),
                      control_failing=int((fail & (wr != w)).sum()), control_passing=int((~fail & (wr != w)).sum())))
    print(json.dumps({"gemma4-31b": res}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("build")
    r = sp.add_parser("run"); r.add_argument("--model", required=True); r.add_argument("--tag", required=True)
    r.add_argument("--workers", type=int, default=8); r.add_argument("--redo-unparsed", action="store_true")
    r.add_argument("--max-tokens", type=int, default=3000); r.add_argument("--limit", type=int)
    r.add_argument("--budget", type=float, help="stop this judge once its row file has cost more than this many dollars")
    z = sp.add_parser("analyze"); z.add_argument("--judges", required=True)
    z.add_argument("--leave-out-reasked", action="store_true", help="exploratory: drop items any judge needed a re-ask on")
    a = ap.parse_args()
    {"build": build, "run": run, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
