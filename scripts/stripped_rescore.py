#!/usr/bin/env python3
"""Held-out patches with leftover added files removed, rescored by the nine paper judges (spec/stripped-files-rescore.md).

  build:   python3 stripped_rescore.py build             -> derived/stripped_patches.jsonl (original pid, stripped patch)
  run:     python3 stripped_rescore.py run --tag gemma4-31b [--redo-unparsed] [--workers 8] [--limit N]
  analyze: python3 stripped_rescore.py analyze > derived/stripped_files_rescore_2026-11-03.json
"""
import argparse, collections, concurrent.futures, json, os, re, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fresh_judging import WRITER_FAMILY, load, patches  # noqa: E402
from open_panel_check import excess, leniency_boot  # noqa: E402
from per_writer_leniency import G, GW, J9  # noqa: E402
from selection_test import rating_prompt  # noqa: E402
from selfjudge_matrix import Q_P1, call, parse  # noqa: E402

MODEL = {"gemma4-31b": "google/gemma-4-31b-it", "gpt-oss-20b": "openai/gpt-oss-20b", "qwen35-9b": "qwen/qwen3.5-9b",
         "glm47-flash": "z-ai/glm-4.7-flash", "qwen3-coder": "qwen/qwen3-coder", "gpt-oss-120b": "openai/gpt-oss-120b",
         "glm-4.5": "z-ai/glm-4.5", "kimi-k2": "moonshotai/kimi-k2", "llama-4-maverick": "meta-llama/llama-4-maverick"}
RUNS = ["main-a", "main-b"]
PATCHES = os.path.join(HERE, "derived", "stripped_patches.jsonl")
BACKUP = (".bak", ".orig", ".tmp", ".backup", ".rej")


def blocks(patch):
    return [b for b in re.split(r"(?m)^(?=diff --git )", patch) if b.strip()]


def path_of(block):
    m = re.match(r"diff --git a/(\S+) b/", block)
    return m.group(1) if m else ""  # text before the first diff header: kept as is


def is_new(block):
    return bool(path_of(block)) and re.search(r"(?m)^new file mode", block.split("\n@@", 1)[0]) is not None


def build(a):
    P = patches(RUNS)
    keep_dirs = collections.defaultdict(set)  # repository -> first path components of modified existing files
    for x in P.values():
        repo = x["iid"].rsplit("-", 1)[0]
        for b in blocks(x["patch"]):
            if not is_new(b):
                keep_dirs[repo].add(path_of(b).split("/")[0])
    n = collections.Counter()
    with open(PATCHES, "w") as f:
        for pid, x in sorted(P.items()):
            repo = x["iid"].rsplit("-", 1)[0]
            kept, removed = [], []
            for b in blocks(x["patch"]):
                p = path_of(b)
                drop = is_new(b) and ("/" not in p or p.split("/")[0] not in keep_dirs[repo] or p.endswith(BACKUP))
                (removed if drop else kept).append(b)
            new = "".join(kept).strip()
            n["changed" if removed else "unchanged"] += 1
            if not new:
                n["empty_after"] += 1
            f.write(json.dumps(dict(pid=pid, iid=x["iid"], writer=x["writer"], issue=x["issue"], patch=new,
                                    removed=[path_of(b) for b in removed])) + "\n")
    print(dict(n))


def run(a):
    rows = [json.loads(l) for l in open(PATCHES)]
    out = os.path.join(HERE, "derived", f"stripped_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    jobs = [(dict(cond="P1", iid=x["iid"], pid=x["pid"], writer=x["writer"], model=MODEL[a.tag]),
             rating_prompt(x["iid"], x, Q_P1)) for x in rows if x["patch"] and x["pid"] not in done][:a.limit]
    print(f"{a.tag}: patches {len(rows)}, new calls {len(jobs)}", flush=True)
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, MODEL[a.tag], pr, a.max_tokens): meta for meta, pr in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); row["parsed"] = parse("P1", row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush()


def analyze(a):
    pids, X0, y, wr, iss, _ = load(J9, RUNS)
    meta = {r["pid"]: r for r in map(json.loads, open(PATCHES))}
    S = collections.defaultdict(dict)
    for t in J9:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"stripped_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]
    keep = np.array([len(S[p]) == len(J9) for p in pids])
    idx = np.where(keep)[0]
    pk = [pids[i] for i in idx]
    X1 = {t: np.array([S[p][t] for p in pk], float) for t in J9}
    X0k = {t: X0[t][idx] for t in J9}
    yk, wrk, isk = y[idx], wr[idx], iss[idx]
    changed = np.array([bool(meta[p]["removed"]) for p in pk])
    out = dict(patches_in_paper_set=len(pids), patches_scored_by_all=int(keep.sum()),
               changed=int(changed.sum()), gemma_changed=int((changed & (wrk == GW)).sum()),
               gemma_failing_changed=int((changed & (wrk == GW) & (yk == 0)).sum()))
    E1 = excess(X1, wrk, WRITER_FAMILY, G, J9); E0 = excess(X0k, wrk, WRITER_FAMILY, G, J9)
    out["leniency_stripped"] = leniency_boot(E1, yk, wrk, isk, GW)
    out["leniency_original_same_patches"] = leniency_boot(E0, yk, wrk, isk, GW)
    # paired difference, original minus stripped, same issue resamples
    fail = (yk == 0) & ~np.isnan(E0) & ~np.isnan(E1)
    own, oth = fail & (wrk == GW), fail & (wrk != GW)
    f = lambda ix, E: E[ix][own[ix]].mean() - E[ix][oth[ix]].mean()
    issues = sorted(set(isk)); by = {i: np.where(isk == i)[0] for i in issues}
    rng = np.random.default_rng(0); B = []
    for _ in range(2000):
        ix = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        if own[ix].any() and oth[ix].any():
            B.append(f(ix, E0) - f(ix, E1))
    al = np.arange(len(yk))
    out["original_minus_stripped"] = dict(value=round(float(f(al, E0) - f(al, E1)), 1),
                                          ci95=[round(float(np.percentile(B, 2.5)), 1), round(float(np.percentile(B, 97.5)), 1)])
    out["run_to_run_mean_abs_diff_unchanged"] = {t: round(float(np.abs(X1[t][~changed] - X0k[t][~changed]).mean()), 2)
                                                 for t in J9}
    gc = changed & (wrk == GW)
    panel = [t for t in J9 if t != G]
    out["gemma_changed_patches_mean_scores"] = dict(
        gemma_original=round(float(X0k[G][gc].mean()), 1), gemma_stripped=round(float(X1[G][gc].mean()), 1),
        panel_original=round(float(np.mean([X0k[t][gc] for t in panel])), 1),
        panel_stripped=round(float(np.mean([X1[t][gc] for t in panel])), 1))
    lv = out["leniency_stripped"]
    out["reading"] = ("confound closed" if lv and lv["value"] >= 8 and lv["ci95"][0] > 0
                      else "leftover files explain part of it")
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("build")
    r = sp.add_parser("run"); r.add_argument("--tag", required=True, choices=sorted(MODEL))
    r.add_argument("--workers", type=int, default=8); r.add_argument("--redo-unparsed", action="store_true")
    r.add_argument("--max-tokens", type=int, default=3000); r.add_argument("--limit", type=int)
    sp.add_parser("analyze")
    a = ap.parse_args()
    {"build": build, "run": run, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
