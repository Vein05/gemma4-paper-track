#!/usr/bin/env python3
"""Does Gemma trust the change or the author? Spec: spec/belief-vs-recognition.md (written before this was run).

E = Gemma's written score minus the outside panel's mean score on the same patch (the panel of
per_writer_leniency.py). Edit similarity = Jaccard of edit sets (file, sign, stripped line) over changed lines in
files that already exist, between a patch and Gemma's patch on the same issue. Failing patches only.

Usage (from scripts/): python3 belief_vs_recognition.py [--cut 0.5] > derived/belief_vs_recognition_2026-11-03.json
"""
import argparse, collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fresh_judging import CONTROL, FAMILY, RUNS, WRITER_FAMILY, WRITERS, load, pid_of, strip_tests  # noqa: E402
from per_writer_leniency import G, GW, J7, J9, LITE_WRITERS, load_rows  # noqa: E402

LITE = os.path.join(HERE, "..", "data", "public", "third-party-lite", "patches.jsonl")


def edit_set(diff):
    out, f, new = set(), None, False
    for ln in diff.splitlines():
        if ln.startswith("diff --git"):
            f, new = None, False
        elif ln.startswith("--- "):
            new = ln.strip() == "--- /dev/null"
        elif ln.startswith("+++ "):
            f = ln[4:].strip()
            f = f[2:] if f.startswith("b/") else f
        elif f and not new and ln[:1] in "+-" and not ln.startswith(("+++", "---")):
            s = "".join(ln[1:].split())
            if s:
                out.add((f, ln[0], s))
    return out


def heldout_patches():
    P = {}
    for r in ("main-a", "main-b"):
        for l in open(os.path.join(RUNS, r, "preds.jsonl")):
            p = json.loads(l); s = strip_tests(p["model_patch"] or "")
            if s:
                P[pid_of(p["instance_id"], GW, s)] = s
    for l in open(CONTROL):
        a = json.loads(l)
        if a["resolved"] is not None:
            w = next(k for k in WRITERS if k in a["writer"].lower()); s = strip_tests(a["patch"] or "")
            if s:
                P[pid_of(a["instance_id"], w, s)] = s
    return P


def excess(X, wr, judges, wfam):
    return np.array([X[G][i] - np.mean([X[m][i] for m in judges if m != G and FAMILY[m] != wfam[wr[i]]])
                     for i in range(len(wr))])


def analyse(E, y, wr, iss, sim, cut):
    fail = y == 0
    own = fail & (wr == GW)
    oth = fail & (wr != GW)
    ok = ~np.isnan(sim)
    same, diff = oth & ok & (sim >= cut), oth & ok & (sim < cut)
    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    has_same = {i for i in issues if same[by[i]].any()}
    has_own = {i for i in issues if own[by[i]].any()}
    both = sorted(has_same & has_own)

    def m(mask, idx):
        v = E[idx][mask[idx]]
        return v.mean() if len(v) else np.nan

    def stats(idx, idx_both):
        return dict(sim_effect=m(same, idx) - m(diff, idx),
                    own_minus_same=m(own, idx_both) - m(same, idx_both),
                    leniency_both=m(own, idx_both) - m(oth, idx_both))

    allx = np.arange(len(y)); bothx = np.concatenate([by[i] for i in both]) if both else np.array([], int)
    point = stats(allx, bothx)
    rng = np.random.default_rng(0); B = collections.defaultdict(list)
    for _ in range(2000):
        pick = rng.choice(issues, len(issues))
        idx = np.concatenate([by[i] for i in pick])
        pb = [i for i in pick if i in has_same and i in has_own]
        ib = np.concatenate([by[i] for i in pb]) if pb else np.array([], int)
        for k, v in stats(idx, ib).items():
            B[k].append(v)
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 1), round(float(np.nanpercentile(v, 97.5)), 1)]
    out = {k: round(float(v), 1) for k, v in point.items()}
    out.update({k + "_ci95": ci(B[k]) for k in point})
    out.update(cut=cut, n_other_failing_same_edit=int(same.sum()), n_other_failing_other_edit=int(diff.sum()),
               n_own_failing=int(own.sum()), n_issues_both=len(both),
               n_own_failing_on_both=int(own[bothx].sum()) if len(bothx) else 0)
    if out["n_other_failing_same_edit"] < 20:
        out["reading"] = "inconclusive (fewer than 20 same-edit patches)"
    elif out["sim_effect_ci95"][0] > 0 and (out["own_minus_same_ci95"][0] <= 0 or
                                           out["own_minus_same"] <= out["leniency_both"] / 2):
        out["reading"] = "belief supported"
    elif out["own_minus_same_ci95"][0] > 0 and out["own_minus_same"] > out["leniency_both"] / 2:
        out["reading"] = "recognition supported"
    else:
        out["reading"] = "inconclusive"
    return out


def similarity(pids, wr, iss, text):
    gem = {}
    for p, w, i in zip(pids, wr, iss):
        if w == GW:
            gem[i] = edit_set(text[p])
    sim = np.full(len(pids), np.nan)
    for k, (p, w, i) in enumerate(zip(pids, wr, iss)):
        g = gem.get(i)
        if g:
            e = edit_set(text[p]); u = g | e
            sim[k] = len(g & e) / len(u) if u else np.nan
    return sim


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cut", type=float, default=0.5); a = ap.parse_args()
    res = {}
    pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
    text = heldout_patches()
    missing = sum(p not in text for p in pids)
    sim = similarity(pids, wr, iss, text)
    res["held-out"] = analyse(excess(X, wr, J9, WRITER_FAMILY), y, wr, iss, sim, a.cut)
    res["held-out"]["patches_without_text"] = missing

    P = {r["pid"]: r for r in map(json.loads, open(LITE))}
    X, y, wr, iss = load_rows(LITE, "lite", J7)
    # the pid order used by load_rows
    Sx = collections.defaultdict(dict)
    for t in J7:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"lite_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                Sx[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in Sx.items() if len(s) == len(J7))
    text = {p: P[p]["patch"] for p in pids}
    sim = similarity(pids, wr, iss, text)
    res["swe-bench-lite"] = analyse(excess(X, wr, J7, LITE_WRITERS), y, wr, iss, sim, a.cut)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
