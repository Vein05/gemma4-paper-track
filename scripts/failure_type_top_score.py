#!/usr/bin/env python3
"""Gemma's top score on wrong fixes and on patches that break a listed test, writer by writer (exploratory,
2026-11-11; spec/hidden-test-and-failure-type-checks.md, part 2).

Other writers: the failing held-out patches of the equally-strong-writers test (`matched_writers.py`, November scores,
patches all nine judges scored) that change code (`failure_census.patch_class` on the patch the judges saw). Failure
type from SWE-bench's public test report in the census rows (`failure_census.py`) for the same entry and issue.
Gemma's own: the split of `failure_types.py analyze` (October scores of `fresh_judging.load`), and the same split on
the November scores where `data/failure-types/test_status.jsonl` has the patch. No network, no model calls.

  python3 failure_type_top_score.py > derived/failure_type_top_score_2026-11-11.json
"""
import collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from api_quickcheck import strip_tests  # noqa: E402
from failure_census import ROWS, patch_class  # noqa: E402
from failure_types import OUT as STATUS, kind  # noqa: E402
from fresh_judging import FAMILY, RUNS, load, pid_of  # noqa: E402
from matched_writers import PATCHES, family_of, scores  # noqa: E402
from per_writer_leniency import G, GW, J9  # noqa: E402

L = lambda p: [json.loads(l) for l in open(p)]
B = 2000
METRICS = ("gemma_share_100", "gemma_mean", "outside_mean", "outside_share_100", "extra_trust")


def per_patch(score, writer_family):
    """The five measures of one patch from {judge: score}."""
    out = [m for m in J9 if m != G and FAMILY[m] != writer_family]
    o = [score[m] for m in out]
    return dict(gemma_share_100=100.0 * (score[G] == 100), gemma_mean=score[G], outside_mean=float(np.mean(o)),
                outside_share_100=100.0 * float(np.mean([v == 100 for v in o])), extra_trust=score[G] - float(np.mean(o)))


def crash(t):
    """Every issue test fails and at least half of the listed other tests fail."""
    return t["issue_pass"] == 0 and t["other_fail"] >= 0.5 * (t["other_pass"] + t["other_fail"]) and t["other_fail"] > 0


def main():
    census = {(r["entry"], r["iid"]): r for r in L(ROWS) if r["report"]}
    meta = {r["pid"]: r for r in L(PATCHES)}
    S, _ = scores("matched", meta)
    pids = sorted(p for p in meta if len(S[p]) == len(J9))
    status = {r["pid"]: r for r in L(STATUS) if r["set"] == "held-out"}

    recs, notes = [], collections.Counter()
    ref = {}
    for p in pids:
        m = meta[p]
        w = m["writer"]
        if patch_class(m["patch"]) != "code":
            notes[f"{w}: holds no fix"] += 1
            continue
        if w == GW:
            st = status.get(p)
            k = kind(st or {})
            if k is None:
                notes["gemma, November scores: no test outcome"] += 1
                continue
            t = dict(issue_pass=st["issue_pass"], issue_fail=st["issue_n"] - st["issue_pass"],
                     other_pass=st["other_pass"], other_fail=st["other_n"] - st["other_pass"])
            typ = "wrong fix" if k == "wrong fix" else "breaks a listed test"
        else:
            c = census.get((w, m["iid"]))
            if c is None:
                notes[f"{w}: no census report"] += 1
                continue
            if not c["applied"] or c["resolved"]:
                notes[f"{w}: census report does not say failing"] += 1
                continue
            t = {k_: c[k_] for k_ in ("issue_pass", "issue_fail", "other_pass", "other_fail")}
            typ = "wrong fix" if (c["issue_fail"] > 0 and c["other_fail"] == 0) else "breaks a listed test"
        recs.append(dict(pid=p, iid=m["iid"], writer=w, family=m["family"], type=typ, tests=t,
                         **per_patch(S[p], m["family"])))

    # Gemma's own, as failure_types.py analyze counts them (October scores; outside = the eight non-Gemma judges).
    pids0, X0, y0, wr0, _, _ = load(J9, ["main-a", "main-b"])
    text = {}
    for run in ("main-a", "main-b"):
        for p in L(os.path.join(RUNS, run, "preds.jsonl")):
            q = strip_tests(p["model_patch"] or "")
            text[pid_of(p["instance_id"], GW, q)] = q
    own0 = []
    for i, p in enumerate(pids0):
        if wr0[i] == GW and y0[i] == 0 and patch_class(text[p]) == "code":
            st = status.get(p, {})
            typ = "wrong fix" if kind(st) == "wrong fix" else "breaks a listed test"
            t = (dict(issue_pass=st["issue_pass"], issue_fail=st["issue_n"] - st["issue_pass"], other_pass=st["other_pass"],
                      other_fail=st["other_n"] - st["other_pass"]) if st.get("parsed") else None)
            own0.append(dict(pid=p, iid=p.split("|")[0], writer=GW, family="gemma", type=typ, tests=t,
                             **per_patch({k: float(X0[k][i]) for k in J9}, "gemma")))

    others = [r for r in recs if r["writer"] != GW]
    own1 = [r for r in recs if r["writer"] == GW]
    writers = sorted({r["writer"] for r in others})
    fams = sorted({family_of(w) for w in writers})

    def cell(rs, typ, metric):
        v = [r[metric] for r in rs if r["type"] == typ]
        return float(np.mean(v)) if v else np.nan

    def diffs(rs):
        """Wrong fix minus breaks a listed test, for each measure: pooled, writer average, family-balanced."""
        out = {}
        for mtr in METRICS:
            d = {w: cell([r for r in rs if r["writer"] == w], "wrong fix", mtr) -
                    cell([r for r in rs if r["writer"] == w], "breaks a listed test", mtr) for w in writers}
            fam = [np.nanmean([d[w] for w in writers if family_of(w) == f]) for f in fams]
            out[mtr] = dict(pooled=cell(rs, "wrong fix", mtr) - cell(rs, "breaks a listed test", mtr),
                            writer_average=float(np.nanmean(list(d.values()))), family_balanced=float(np.nanmean(fam)),
                            **{f"writer {w}": d[w] for w in writers})
        return out

    def boot(rs, fn):
        iss = sorted({r["iid"] for r in rs}); by = collections.defaultdict(list)
        for r in rs:
            by[r["iid"]].append(r)
        rng = np.random.default_rng(0); acc = collections.defaultdict(list)
        for _ in range(B):
            sample = [r for i in rng.choice(iss, len(iss)) for r in by[i]]
            for k, v in flat(fn(sample)).items():
                acc[k].append(v)
        point = flat(fn(rs))
        return {k: dict(value=round(v, 1), ci95=[round(float(np.nanpercentile(acc[k], 2.5)), 1),
                                                 round(float(np.nanpercentile(acc[k], 97.5)), 1)]) for k, v in point.items()}

    def flat(d, pre=""):
        out = {}
        for k, v in d.items():
            if isinstance(v, dict):
                out.update(flat(v, f"{pre}{k} | "))
            else:
                out[f"{pre}{k}"] = float(v)
        return out

    def own_diff(rs):
        return {m: cell(rs, "wrong fix", m) - cell(rs, "breaks a listed test", m) for m in METRICS}

    def table(rs):
        out = {}
        for typ in ("wrong fix", "breaks a listed test"):
            sub = [r for r in rs if r["type"] == typ]
            out[typ] = dict(n=len(sub), **{m: round(cell(rs, typ, m), 1) for m in METRICS})
        return out

    def crashes(rs):
        low = [r for r in rs if r["type"] == "breaks a listed test" and r["gemma_mean"] < 50]
        hi = [r for r in rs if r["type"] == "breaks a listed test" and r["gemma_mean"] == 100]
        n = lambda v: dict(n=len(v), with_tests=sum(r["tests"] is not None for r in v),
                           every_issue_test_fails_and_half_or_more_other_tests_fail=sum(bool(r["tests"]) and crash(r["tests"]) for r in v),
                           every_issue_test_fails=sum(bool(r["tests"]) and r["tests"]["issue_pass"] == 0 for r in v),
                           some_issue_test_passes=sum(bool(r["tests"]) and r["tests"]["issue_pass"] > 0 for r in v))
        return dict(gemma_below_50=n(low), gemma_100=n(hi))

    res = dict(exploratory=True, spec="spec/hidden-test-and-failure-type-checks.md",
               left_out=dict(notes.most_common()),
               per_writer={w: dict(family=family_of(w), **table([r for r in others if r["writer"] == w])) for w in writers},
               other_writers_pooled=table(others),
               gemma_own_october_scores_failure_types_split=table(own0),
               gemma_own_november_scores=table(own1),
               differences_wrong_fix_minus_breaks_a_listed_test=dict(
                   other_writers=boot(others, diffs),
                   gemma_own_october_scores=boot(own0, own_diff),
                   gemma_own_november_scores=boot(own1, own_diff)),
               obvious_crashes=dict(other_writers=crashes(others), gemma_own_october_scores=crashes(own0),
                                    per_writer={w: crashes([r for r in others if r["writer"] == w]) for w in writers}),
               families=fams, issues_other_writers=len({r["iid"] for r in others}))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
