#!/usr/bin/env python3
"""The two comparisons of Section 3.1 without the failing patches that hold no fix (exploratory, 2026-11-10).

Some failing patches change no existing source file: they only add files such as a reproduction script. Gemma has 8
among its failing held-out patches and scores each of them 0, and the equally strong writers have 5 among 526. This
script repeats the mixed-strength comparison (fresh_judging.py analyze) and the equally-strong-writers comparison
(matched_writers.py analyze) on the failing patches that change code (failure_census.patch_class, applied to the
patch the judges saw). The planned analyses use all failing patches, and the paper reports those.

Usage: python3 code_changing_patches.py > derived/code_changing_patches_2026-11-10.json
"""
import collections, contextlib, io, json, os, sys, tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fresh_judging as fj  # noqa: E402
import matched_writers as mw  # noqa: E402
from api_quickcheck import strip_tests  # noqa: E402
from failure_census import patch_class  # noqa: E402
from per_writer_leniency import G, GW, J9  # noqa: E402

L = lambda p: [json.loads(l) for l in open(p)]


def mixed_strength():
    """Own minus the five mixed-strength writers on failing held-out patches, as fresh_judging.py analyze computes it."""
    pids, X, y, wr, iss, _ = fj.load(J9, ["main-a", "main-b"])
    outside = [k for k in J9 if k != G and fj.FAMILY[k] != fj.WRITER_FAMILY[GW]]
    D = np.array([X[G][i] - np.mean([X[k][i] for k in outside if fj.FAMILY[k] != fj.WRITER_FAMILY[wr[i]]])
                  for i in range(len(pids))])
    text = {}
    for run in ("main-a", "main-b"):
        for p in L(os.path.join(fj.RUNS, run, "preds.jsonl")):
            q = strip_tests(p["model_patch"] or "")
            text[fj.pid_of(p["instance_id"], GW, q)] = q
    for c in L(fj.CONTROL):
        name = next((k for k in fj.WRITERS if k in c["writer"].lower()), None)
        if name is not None:
            q = strip_tests(c["patch"] or "")
            text[fj.pid_of(c["instance_id"], name, q)] = q
    code = np.array([patch_class(text[p]) == "code" for p in pids])
    y, wr, iss = np.array(y), np.array(wr), np.array(iss)
    issues = sorted(set(iss))
    by = {i: np.where(iss == i)[0] for i in issues}

    def gap(idx, keep):
        sel = idx[(y[idx] == 0) & keep[idx]]
        return D[sel[wr[sel] == GW]].mean() - D[sel[wr[sel] != GW]].mean()

    out = {}
    for name, keep in (("all_failing_patches", np.ones(len(pids), bool)), ("failing_patches_that_change_code", code)):
        rng = np.random.default_rng(0)
        boot = [gap(np.concatenate([by[i] for i in rng.choice(issues, len(issues))]), keep) for _ in range(2000)]
        fail = (y == 0) & keep
        out[name] = dict(own=int((fail & (wr == GW)).sum()), others=int((fail & (wr != GW)).sum()),
                         value=round(float(gap(np.arange(len(pids)), keep)), 1),
                         ci95=[round(float(np.percentile(boot, 2.5)), 1), round(float(np.percentile(boot, 97.5)), 1)],
                         own_scored_100=round(float((X[G][fail & (wr == GW)] == 100).mean()), 3))
    out["left_out_by_writer"] = dict(collections.Counter(wr[(y == 0) & ~code]).most_common())
    return out


def equally_strong():
    """matched_writers.py analyze on all failing patches of that test and on those that change code."""
    rows = L(mw.PATCHES)
    keep = [r for r in rows if patch_class(r["patch"]) == "code"]
    left_out = collections.Counter(r["writer"] for r in rows if patch_class(r["patch"]) != "code")

    def run(path):
        mw.PATCHES = path
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mw.analyze(None)
        r = json.loads(buf.getvalue())[G]
        pick = lambda k: r[k]
        return dict(patches=r["patches_in_set"],
                    extra_trust=pick("extra_trust_own_minus_matched_family_balanced"),
                    extra_trust_without_google=pick("extra_trust_own_minus_matched_without_google"),
                    extra_trust_without_openai=pick("extra_trust_own_minus_matched_without_gpt-oss"),
                    scored_100=pick("share_100_own_minus_matched_family_balanced"),
                    own_scored_100=r["per_writer"][GW]["gemma_share_100"], own_failing=r["per_writer"][GW]["failing"])

    original = mw.PATCHES
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "patches.jsonl")
        with open(path, "w") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")
        out = dict(all_failing_patches=run(original), failing_patches_that_change_code=run(path))
    out["left_out_by_writer"] = dict(left_out.most_common())
    return out


if __name__ == "__main__":
    m, e = mixed_strength(), equally_strong()
    share = lambda k: round(e[k]["extra_trust"]["value"] / m[k]["value"], 2)
    print(json.dumps(dict(
        mixed_strength_writers=m, equally_strong_writers=e,
        share_of_the_mixed_strength_gap_that_remains={k: share(k) for k in ("all_failing_patches",
                                                                           "failing_patches_that_change_code")}), indent=1))
