#!/usr/bin/env python3
"""Addendum 1 of spec/belief-vs-recognition.md: Test A (other writers' edits as the reference) and Test B (each
judge on its own edits, held-out only). Failing patches, similarity cut-off 0.5, 2,000 issue resamples, seed 0.

Usage (from scripts/): python3 belief_reference_tests.py > derived/belief_reference_tests_2026-11-03.json
"""
import collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from belief_vs_recognition import LITE, edit_set, heldout_patches  # noqa: E402
from fresh_judging import FAMILY, OWN, WRITER_FAMILY, load  # noqa: E402
from per_writer_leniency import G, GW, J7, J9, LITE_WRITERS, load_rows  # noqa: E402

CUT = 0.5


def sim_to(ref, pids, wr, iss, text):
    """Similarity of each patch to writer ref's patch on the same issue (nan if none or empty)."""
    R = {i: edit_set(text[p]) for p, w, i in zip(pids, wr, iss) if w == ref}
    s = np.full(len(pids), np.nan)
    for k, (p, i) in enumerate(zip(pids, iss)):
        g = R.get(i)
        if g:
            e = edit_set(text[p]); s[k] = len(g & e) / len(g | e)
    return s


def excess(X, wr, judges, wfam, k):
    excl = {k} if k == G else {k, G}
    return np.array([X[k][i] - np.mean([X[m][i] for m in judges if m not in excl and FAMILY[m] != wfam[wr[i]]])
                     for i in range(len(wr))])


def boot(iss, fn):
    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); B = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        for k, v in fn(idx).items():
            B[k].append(v)
    point = fn(np.arange(len(iss)))
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 1), round(float(np.nanpercentile(v, 97.5)), 1)]
    return {k: dict(value=round(float(v), 1), ci95=ci(B[k])) for k, v in point.items()}


def diffmean(E, a, b, idx):
    x, z = E[idx][a[idx]], E[idx][b[idx]]
    return x.mean() - z.mean() if len(x) and len(z) else np.nan


def test_a(E, y, wr, iss, pids, text):
    fail = y == 0
    writers = sorted(set(wr))
    S = {r: sim_to(r, pids, wr, iss, text) for r in writers}
    masks, counts = {}, {}
    for r in writers:
        pool = fail & (wr != r) & (wr != GW) & ~np.isnan(S[r])
        masks[r] = (pool & (S[r] >= CUT), pool & (S[r] < CUT))
        counts[r] = int(masks[r][0].sum())
    others = [r for r in writers if r != GW]

    def fn(idx):
        eff = {r: diffmean(E, *masks[r], idx) for r in writers}
        mo = np.nanmean([eff[r] for r in others])
        out = {f"effect_{r}": eff[r] for r in writers}
        out.update(mean_other_writers=mo, delta_gemma_minus_mean_other=eff[GW] - mo)
        return out

    res = boot(iss, fn); res["same_edit_counts"] = counts
    d, mo = res["delta_gemma_minus_mean_other"]["ci95"], res["mean_other_writers"]["ci95"]
    res["reading"] = ("Gemma's own edit" if d[0] > 0 else
                      "common fix" if d[0] <= 0 <= d[1] and mo[0] > 0 else "inconclusive")
    return res


def test_b(X, y, wr, iss, pids, text):
    fail = y == 0
    judges = [j for j in OWN if j in J9]
    masks, counts = {}, {}
    E = {}
    for k in judges:
        w = OWN[k]; s = sim_to(w, pids, wr, iss, text)
        E[k] = excess(X, wr, J9, WRITER_FAMILY, k)
        pool = fail & (wr != w) & ~np.isnan(s)
        own = fail & (wr == w)
        masks[k] = (pool & (s >= CUT), pool & (s < CUT), own)
        counts[k] = int(masks[k][0].sum())
    others = [k for k in judges if k != G]

    def fn(idx):
        out = {}
        for k in judges:
            same, diff, own = masks[k]
            out[f"same_minus_other_edit_{k}"] = diffmean(E[k], same, diff, idx)
            out[f"own_minus_same_edit_{k}"] = diffmean(E[k], own, same, idx)
        mo = np.nanmean([out[f"same_minus_other_edit_{k}"] for k in others])
        out.update(mean_other_judges=mo, gemma_minus_mean_other=out[f"same_minus_other_edit_{G}"] - mo)
        return out

    res = boot(iss, fn); res["same_edit_counts"] = counts
    d, mo = res["gemma_minus_mean_other"]["ci95"], res["mean_other_judges"]["ci95"]
    res["reading"] = ("specific to Gemma" if d[0] > 0 else
                      "every judge trusts its own edits" if d[0] <= 0 <= d[1] and mo[0] > 0 else "inconclusive")
    return res


def main():
    res = {}
    pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
    text = heldout_patches()
    Eg = excess(X, wr, J9, WRITER_FAMILY, G)
    res["held-out"] = dict(test_a=test_a(Eg, y, wr, iss, pids, text), test_b=test_b(X, y, wr, iss, pids, text))

    P = {r["pid"]: r for r in map(json.loads, open(LITE))}
    X, y, wr, iss = load_rows(LITE, "lite", J7)
    Sx = collections.defaultdict(dict)
    for t in J7:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"lite_{t}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                Sx[r["pid"]][t] = r["parsed"]
    pids = sorted(p for p, s in Sx.items() if len(s) == len(J7))
    text = {p: P[p]["patch"] for p in pids}
    Eg = excess(X, wr, J7, LITE_WRITERS, G)
    res["swe-bench-lite"] = dict(test_a=test_a(Eg, y, wr, iss, pids, text))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
