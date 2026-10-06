#!/usr/bin/env python3
"""Judging of the fresh-issue patches (spec/fresh-judging-interim.md; same prompt, settings and parser as
scripts/self_preference.py).

run: one reasoning-first rating per patch for Gemma 4's mini-SWE-agent patches in the given run directories and the
  five control writers' patches on the same issues. Labels are not needed to judge; they are joined in analyze.
  Rows: derived/fresh_<tag>.jsonl (resumes; --redo-unparsed asks unparsed answers once more).
analyze: Gemma's self-judging gap (as in self_judging_replication.py), patch-matched leniency (raw and rank-normalised;
  added after the spec's freeze, see its 2026-10-06 12:05 addendum) and rubber-stamp rates with the given judges.

Usage:
  python3 fresh_judging.py run --model google/gemma-4-31b-it --tag gemma4-31b --runs main-a [--workers 8]
  python3 fresh_judging.py analyze --judges gemma4-31b,gpt-oss-120b,qwen35-9b --runs main-a > derived/<name>.json
"""
import argparse, collections, concurrent.futures, hashlib, json, os, sys

import numpy as np
from scipy.stats import rankdata

sys.path.insert(0, os.path.dirname(__file__))
from api_quickcheck import strip_tests  # noqa: E402
from live_data import MAX_CHARS  # noqa: E402
from selection_test import rating_prompt  # noqa: E402
from selfjudge_matrix import Q_P1, call, parse  # noqa: E402
from self_judging_replication import auroc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
RUNS = os.path.join(ROOT, "data", "mcsr-runs")
CONTROL = os.path.join(ROOT, "data", "public", "swe-bench-verified-control-fresh", "attempts.jsonl")
WRITERS = ("gpt-oss-120b", "glm-4.5", "qwen3-coder", "llama-4-maverick", "kimi-k2")
FAMILY = {"gemma4-31b": "gemma", "gpt-oss-20b": "gpt-oss", "qwen35-9b": "qwen", "glm47-flash": "glm",
          "qwen3-coder": "qwen", "gpt-oss-120b": "gpt-oss", "glm-4.5": "glm", "kimi-k2": "kimi",
          "llama-4-maverick": "llama"}
WRITER_FAMILY = {"gemma-4-31b": "gemma", "qwen3-coder": "qwen", "gpt-oss-120b": "gpt-oss", "glm-4.5": "glm",
                 "kimi-k2": "kimi", "llama-4-maverick": "llama"}
OWN = {"qwen3-coder": "qwen3-coder", "gpt-oss-120b": "gpt-oss-120b", "glm-4.5": "glm-4.5", "kimi-k2": "kimi-k2",
       "llama-4-maverick": "llama-4-maverick", "gemma4-31b": "gemma-4-31b"}


def pid_of(iid, writer, patch):
    return f"{iid}|{writer}|{hashlib.md5(patch.encode()).hexdigest()[:8]}"


def patches(runs):
    """Gemma's non-empty patches in the run directories, and the control writers' patches on the same issues."""
    from datasets import load_dataset
    gem = {}
    for r in runs:
        for l in open(os.path.join(RUNS, r, "preds.jsonl")):
            p = json.loads(l)
            gem[p["instance_id"]] = p["model_patch"]
    issues = {r["instance_id"]: r["problem_statement"]
              for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test") if r["instance_id"] in gem}
    out = {}
    def add(iid, writer, patch, y):
        p = strip_tests(patch or "")
        if p and len(p) <= MAX_CHARS:
            out.setdefault(pid_of(iid, writer, p), dict(iid=iid, writer=writer, patch=p, y=y, issue=issues[iid]))
    for iid, patch in gem.items():
        add(iid, "gemma-4-31b", patch, None)
    for l in open(CONTROL):
        a = json.loads(l)
        if a["instance_id"] in gem and a["resolved"] is not None:
            w = next(k for k in WRITERS if k in a["writer"].lower())
            add(a["instance_id"], w, a["patch"], int(a["resolved"]))
    return out


def run(a):
    P = patches(a.runs.split(","))
    out = os.path.join(HERE, "derived", f"fresh_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    jobs = [(dict(cond="P1", iid=x["iid"], pid=pid, writer=x["writer"], model=a.model), rating_prompt(x["iid"], x, Q_P1))
            for pid, x in sorted(P.items()) if pid not in done][:a.limit]
    print(f"{a.model}: patches {len(P)}, new calls {len(jobs)}", flush=True)
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, a.model, pr, a.max_tokens): meta for meta, pr in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); row["parsed"] = parse("P1", row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush()


def labels(runs):
    """Gemma's labels from Magnolia, on issues whose reference patch resolves there (spec addendum)."""
    ref = {}
    for g in ("gold", "gold-retry", "gold-redo"):  # later files override earlier ones
        f = os.path.join(RUNS, g, "labels.jsonl")
        for l in open(f) if os.path.exists(f) else []:
            x = json.loads(l)
            if x["status"] == "graded" or g == "gold":
                ref[x["instance_id"]] = bool(x["resolved"])
    lab = {}
    for r in runs:
        for l in open(os.path.join(RUNS, r, "labels.jsonl")):
            x = json.loads(l)
            if x["status"] in ("graded", "patch_apply_failed") and ref.get(x["instance_id"]):
                lab[x["instance_id"]] = int(bool(x["resolved"]))
    return lab


def analyze(a):
    judges, runs = a.judges.split(","), a.runs.split(",")
    lab = labels(runs)
    S, meta = collections.defaultdict(dict), {}
    for t in judges:
        for l in open(os.path.join(HERE, "derived", f"fresh_{t}.jsonl")):
            r = json.loads(l)
            if r.get("err") is None and r.get("parsed") is not None and r["iid"] in lab:
                S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], r["writer"])
    ctrl = {}
    for l in open(CONTROL):
        c = json.loads(l)
        if c["resolved"] is not None:
            w = next(k for k in WRITERS if k in c["writer"].lower())
            ctrl[pid_of(c["instance_id"], w, strip_tests(c["patch"] or ""))] = int(c["resolved"])
    pids = sorted(p for p, s in S.items() if len(s) == len(judges))
    y = np.array([lab[meta[p][0]] if meta[p][1] == "gemma-4-31b" else ctrl[p] for p in pids])
    wr = np.array([meta[p][1] for p in pids]); iss = np.array([meta[p][0] for p in pids])
    X = {t: np.array([S[p][t] for p in pids], float) for t in judges}
    j, w = "gemma4-31b", "gemma-4-31b"
    outside = [k for k in judges if k != j and FAMILY[k] != WRITER_FAMILY[w]]

    def measures(idx):
        own, rest = idx[wr[idx] == w], idx[wr[idx] != w]
        self_drop = auroc(X[j][rest], y[rest]) - auroc(X[j][own], y[own])
        drops = {}
        for k in outside:
            rk = rest if k not in OWN else rest[wr[rest] != OWN[k]]
            drops[k] = auroc(X[k][rk], y[rk]) - auroc(X[k][own], y[own])
        base = float(np.mean(list(drops.values())))
        return dict(gemma_auroc_own=auroc(X[j][own], y[own]), gemma_auroc_control=auroc(X[j][rest], y[rest]),
                    self_drop=self_drop, baseline_drop=base, gap=self_drop - base,
                    **{f"drop_{k}": v for k, v in drops.items()})

    R = {t: (rankdata(X[t]) - 1) / (len(pids) - 1) for t in judges}  # per-judge mid-ranks scaled to 0-1
    ks_of = [[k for k in outside if FAMILY[k] != WRITER_FAMILY[v]] for v in wr]  # outside judges per patch
    D = {name: np.array([Z[j][i] - np.mean([Z[k][i] for k in ks_of[i]]) for i in range(len(pids))])
         for name, Z in (("raw", X), ("rank", R))}

    def leniency(idx):
        """Gemma minus outside judges on the same patch: own minus control writers', failing and passing patches
        (addendum 2026-10-06 12:05 to spec/fresh-replication.md, added after the freeze)."""
        out = {}
        for name, d in D.items():
            for lab_, yy in (("failing", 0), ("passing", 1)):
                sel = idx[y[idx] == yy]
                own, rest = d[sel[wr[sel] == w]], d[sel[wr[sel] != w]]
                out[f"lenient_{name}_{lab_}_own"] = own.mean()
                out[f"lenient_{name}_{lab_}_control"] = rest.mean()
                out[f"lenient_{name}_{lab_}_difference"] = own.mean() - rest.mean()
        return out

    allidx = np.arange(len(pids))
    point = measures(allidx) | leniency(allidx)
    issues = sorted(set(iss)); by_issue = {i: np.where(iss == i)[0] for i in issues}
    BOOT = ["self_drop", "baseline_drop", "gap"] + [f"lenient_{n}_{f}_difference" for n in D for f in ("failing", "passing")]
    rng = np.random.default_rng(0); boot = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by_issue[i] for i in rng.choice(issues, len(issues))])
        m = measures(idx) | leniency(idx)
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
    res.update(judges=judges, outside_judges=outside, runs=runs, issues=len(issues), patches_rated_by_all=len(pids),
               patches_left_out=len(S) - len(pids),
               n=dict(own_failing=int((fail & (wr == w)).sum()), own_passing=int((~fail & (wr == w)).sum()),
                      control_failing=int((fail & (wr != w)).sum()), control_passing=int((~fail & (wr != w)).sum())))
    print(json.dumps({"gemma4-31b": res}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--model", required=True); r.add_argument("--tag", required=True)
    r.add_argument("--runs", required=True); r.add_argument("--workers", type=int, default=8)
    r.add_argument("--redo-unparsed", action="store_true"); r.add_argument("--max-tokens", type=int, default=3000)
    r.add_argument("--limit", type=int, help="test pass only: at most this many new calls")
    z = sp.add_parser("analyze"); z.add_argument("--judges", required=True); z.add_argument("--runs", required=True)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else analyze(a)


if __name__ == "__main__":
    main()
