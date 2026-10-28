#!/usr/bin/env python3
"""Breaking Gemma 4's tie at 100 without a second model, and the gain of every second-judge check (2026-10-22,
notes/human-interest-2026-10-22/). No model calls.

Tie-breaks: rank Gemma's own patches by Gemma's score; inside equal scores, a lower value of the tie-break ranks
higher. The three candidates were fixed on the Mini issues before any held-out value was computed
(notes/human-interest-2026-10-22/lane-fix/prereg_task2.txt): concern words in Gemma's answer, the length of Gemma's
answer, and the number of model calls in Gemma's agent run (only our own runs have these, so its Mini value comes from
the 42 matched-harness patches). Submitting the top share uses accept_decision.accept, so the numbers sit beside the
paper's Section 3.2 table.

All checks: each of the eight outside judges alone and averaged with Gemma's ranks (16 checks), top quarter and top
half of Gemma's 180 held-out patches. The paper's table shows three of them, chosen after their AUROCs were seen; the
median over all 16 does not depend on that choice.

Usage: python3 tie_break.py > derived/tie_break_2026-10-22.json
"""
import collections, glob, json, os, re

import numpy as np
from scipy.stats import rankdata

from accept_decision import accept
from outside_judge_check import fresh_set, original_set
from self_judging_replication import JUDGES, auroc

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "data", "mcsr-runs")
G, GW, B = "gemma4-31b", "gemma-4-31b", 2000
OUTSIDE = [t for t in JUDGES if t != G]
# concern_all of notes/human-interest-2026-10-22/lane-rationales/feats.py, fixed before the held-out test
CONCERN = [r"\bhowever\b", r"\bbut\b", r"\bmissing\b|\bmisses\b|\bmissed\b", r"\bbugs?\b|\bbuggy\b",
           r"\bincorrect(ly)?\b|\bwrong(ly)?\b", r"\bregress\w*", r"\bedge[- ]cases?\b|\bcorner[- ]cases?\b",
           r"\bunrelated\b|\bunnecessar\w+|\bextraneous\b|\bnoise\b|\bclutter\w*|\bleftover\b|\bartifacts?\b",
           r"\bdebug\w*|\breproduc\w+ (script|file)|\bscratch\b|\btemporary\b|\bhelper script",
           r"\bfail(s|ed|ure|ing)?\b|\bbreak(s|ing)?\b|\bbroken\b|\bcrash\w*|\bwill not\b|\bwon't\b|\bdoes not (handle|work|address|cover|fix|account)|\bdoesn't (handle|work|address|cover|fix|account)",
           r"\brisk\w*|\bconcern\w*|\bproblem\w*|\bflaw\w*|\bfragile\b|\bred flag\b|\bcritical\b|\bunfortunately\b|\bincomplete\b|\binsufficient\b|\bhack\w*|\bbrittle\b",
           r"\bunexpected\w*|\bunintended\b|\bside[- ]effects?\b"]
CONCERN = [re.compile(p, re.I) for p in CONCERN]


def body(t):
    """Gemma's answer without the final SCORE line."""
    return re.sub(r"(?is)\n*\**SCORE:?\**\s*:?\s*\**\s*\d+.*$", "", t or "").strip()


def gemma_answers():
    """Gemma-as-judge answer per patch: last parsed row (re-asks supersede); reused Mini ratings take their text from
    the own-attempts run they were copied from."""
    R = {}
    for l in open(os.path.join(HERE, "derived", f"fresh_{G}.jsonl")):
        r = json.loads(l)
        if r.get("writer") == GW and r.get("err") is None and r.get("parsed") is not None:
            R[r["pid"]] = r["content"]
    sel = {}
    for l in open(os.path.join(HERE, "derived", f"selection-own_{G}.jsonl")):
        r = json.loads(l)
        if r.get("cond") == "P1" and r.get("err") is None and r.get("parsed") is not None:
            sel[r["pid"]] = r
    for l in open(os.path.join(HERE, "derived", f"selfpref_{G}.jsonl")):
        r = json.loads(l)
        if r.get("writer") == GW and r.get("err") is None and r.get("parsed") is not None:
            if r.get("reused"):
                assert sel[r["pid"]]["parsed"] == r["parsed"]
                R[r["pid"]] = sel[r["pid"]]["content"]
            else:
                R[r["pid"]] = r["content"]
    return R


def n_calls(runs):
    d = {}
    for r in runs:
        for f in glob.glob(os.path.join(RUNS, r, "trajs", "*.json")):
            t = json.load(open(f)); d[t["instance_id"]] = t["n_calls"]
    return d


def patch_set(S, meta, runs, A):
    pids = sorted(p for p, s in S.items() if len(s) == len(JUDGES))
    d = dict(pids=pids, iss=np.array([meta[p][0] for p in pids]), y=np.array([meta[p][1] for p in pids]),
             X={t: np.array([S[p][t] for p in pids], float) for t in JUDGES})
    texts = [body(A[p]) for p in pids]
    d["concern_words"] = np.array([sum(len(c.findall(t)) for c in CONCERN) for t in texts], float)
    d["answer_words"] = np.array([len(t.split()) for t in texts], float)
    if runs:
        nc = n_calls(runs)
        d["model_calls"] = np.array([nc[i] for i in d["iss"]], float)
    return d


def cat(a, b):
    return dict(pids=a["pids"] + b["pids"], **{k: np.concatenate([a[k], b[k]]) for k in ("iss", "y", "concern_words", "answer_words")},
                X={t: np.concatenate([a["X"][t], b["X"][t]]) for t in JUDGES})


def boot(iss, B=B, seed=0):
    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(seed)
    for _ in range(B):
        yield np.concatenate([by[i] for i in rng.choice(issues, len(issues))])


def ci(v):
    return [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]


def precision(score, y, a):
    p, f = accept(score, y, a)
    return p / (p + f)


def main():
    A = gemma_answers()
    ho = patch_set(*fresh_set(["main-a", "main-b"]), ["main-a", "main-b"], A)
    matched = patch_set(*fresh_set(["mini50"]), ["mini50"], A)
    mini = cat(patch_set(*original_set(), None, A), matched)
    y, tie = ho["y"], ho["X"][G] == 100
    out = dict(heldout=dict(patches=len(y), passing=int(y.sum()), gemma_100=int(tie.sum()), passing_at_100=int(y[tie].sum())))

    # tie-breaks: inside-tie AUROC on the Mini patches they were chosen on, then the held-out test
    out["tie_breaks"] = {}
    for feat, M in (("concern_words", mini), ("answer_words", mini), ("model_calls", matched)):
        mt = M["X"][G] == 100
        s = ho["X"][G] * 1e6 - ho[feat]
        r = dict(mini_tied_patches=int(mt.sum()), mini_auroc_inside_tie=round(float(auroc(-M[feat][mt], M["y"][mt])), 3),
                 heldout_auroc_inside_tie=round(float(auroc(-ho[feat][tie], y[tie])), 3),
                 heldout_auroc_inside_tie_ci95=ci([auroc(-ho[feat][tie][i], y[tie][i]) for i in boot(ho["iss"][tie])]),
                 heldout_mean_passing_failing_at_100=[round(float(ho[feat][tie & (y == 1)].mean()), 1),
                                                      round(float(ho[feat][tie & (y == 0)].mean()), 1)])
        for a in (0.25, 0.5):
            g = lambda idx: precision(ho["X"][G][idx], y[idx], a)
            d = [precision(s[i], y[i], a) - g(i) for i in boot(ho["iss"])]
            pt = precision(s, y, a)
            r[f"accept_{int(a * 100)}"] = dict(precision=round(float(pt), 3),
                                               precision_minus_gemma=round(float(pt - g(np.arange(len(y)))), 3), ci95=ci(d))
        out["tie_breaks"][feat] = r
    # the deterministic form of the model-call rule: Gemma scores 100 and the run used at most k model calls
    out["model_call_rule"] = {}
    for k in (8, 9, 10, 11):
        acc = tie & (ho["model_calls"] <= k)
        out["model_call_rule"][f"at_most_{k}"] = dict(accepted=int(acc.sum()), share=round(float(acc.mean()), 3),
                                                      precision=round(float(y[acc].mean()), 3))
    out["model_calls_spearman_with_outside_mean_inside_tie"] = round(float(np.corrcoef(
        rankdata(ho["model_calls"][tie]), rankdata(np.mean([ho["X"][t][tie] for t in OUTSIDE], axis=0)))[0, 1]), 3)
    # the two best single outside judges against the model-call tie-break (exploratory, added after the test)
    tb = ho["X"][G] * 1e6 - ho["model_calls"]
    out["judge_minus_model_call_tie_break"] = {}
    for t in ("glm-4.5", "kimi-k2"):
        for a in (0.25, 0.5):
            d = [precision(ho["X"][t][i], y[i], a) - precision(tb[i], y[i], a) for i in boot(ho["iss"])]
            out["judge_minus_model_call_tie_break"][f"{t}_accept_{int(a * 100)}"] = dict(
                difference=round(float(precision(ho["X"][t], y, a) - precision(tb, y, a)), 3), ci95=ci(d))

    # all 16 second-judge checks
    n = len(y)
    checks = {t: ho["X"][t] for t in OUTSIDE}
    checks.update({f"gemma_plus_{t}": (rankdata(ho["X"][G]) / n + rankdata(ho["X"][t]) / n) / 2 for t in OUTSIDE})
    out["all_checks"] = {}
    for a in (0.25, 0.5):
        gains, lows = {}, 0
        for c, s in checks.items():
            d = [precision(s[i], y[i], a) - precision(ho["X"][G][i], y[i], a) for i in boot(ho["iss"])]
            gains[c] = dict(gain=round(float(precision(s, y, a) - precision(ho["X"][G], y, a)), 3), ci95=ci(d))
            lows += ci(d)[0] > 0
        out["all_checks"][f"accept_{int(a * 100)}"] = dict(
            median_gain=round(float(np.median([v["gain"] for v in gains.values()])), 3),
            checks_with_lower_bound_above_zero=int(lows), checks=gains)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
