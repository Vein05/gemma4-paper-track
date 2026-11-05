#!/usr/bin/env python3
"""Does a judge's extra trust in its own failing patches survive its general leniency and the plausibility of the
patch? (2026-11-04, exploratory: chosen after the strong-writer analysis and the literature scout's note
`notes/lit-why-rubber-stamping-2026-11-04.md` were seen; the model and the reading below were fixed before the
numbers were computed.)

For each judge J that also wrote patches, on FAILING patches only:

    score_J(patch) = a + b * panel_J(patch) + c * own_J(patch) + e

panel_J = mean score of the other judges on the same patch (Gemma excluded for non-Gemma judges, and judges of the
writer's family excluded, as in per_writer_leniency.py); own_J = 1 if the patch's writer is J's own model.

- "general leniency" = a + (b - 1) * mean(panel) on other writers' failing patches, i.e. the judge's mean score minus
  the panel's on other writers' failing patches (reported directly as that mean difference);
- b = how steeply the judge follows plausibility (b < 1 means it compresses scores, as a ceiling at 100 would);
- c = the own-writer term: points of extra trust on the judge's own failing patches at equal plausibility.

Variants, all on failing patches: (i) the linear model above; (ii) the same with the writer's pass rate on the set
added (strength of the writer); (iii) a ceiling-aware version: logistic regression of (score == 100) on panel and
own, reported as the own-writer odds ratio and as the own-minus-others difference in the share of 100s at the mean
panel score.

Reading, fixed before running: rubber-stamping proper for judge J = c with the 95% interval above 0 (held-out), and
for Gemma also on SWE-bench Lite and LiveCodeBench, where only Gemma is both judge and writer. If Gemma's c holds and
the other five judges' intervals include 0, the own-patch term is Gemma-specific after general leniency and
plausibility are removed. If Gemma's c loses its interval once the writer's pass rate is added, "own" reduces to
"strong writer".

Intervals: 2,000 bootstrap resamples of issues, seed 0. Usage:
    python3 own_term_regression.py > derived/own_term_regression_2026-11-04.json
"""
import collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fresh_judging import FAMILY, OWN, WRITER_FAMILY, load  # noqa: E402
from per_writer_leniency import G, GW, J6, J7, J9, LCB_WRITERS, LITE_WRITERS, load_rows  # noqa: E402

BOOT, SEED = 2000, 0


def logistic(Xm, t, iters=200):
    """Plain Newton logistic regression with a tiny ridge; returns coefficients."""
    w = np.zeros(Xm.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xm @ w))
        g = Xm.T @ (p - t) + 1e-4 * w
        Hm = (Xm * (p * (1 - p))[:, None]).T @ Xm + 1e-4 * np.eye(Xm.shape[1])
        step = np.linalg.solve(Hm, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def fit(idx, s, panel, own, strength):
    f = idx
    pm = panel[f].mean()
    Xl = np.column_stack([np.ones(len(f)), panel[f] - pm, own[f]])
    a, b, c = np.linalg.lstsq(Xl, s[f], rcond=None)[0]
    Xs = np.column_stack([Xl, strength[f] - strength[f].mean()])
    a2, b2, c2, d2 = np.linalg.lstsq(Xs, s[f], rcond=None)[0]
    t = (s[f] == 100).astype(float)
    r = dict(general_leniency=float((s[f] - panel[f])[own[f] == 0].mean()),
             slope=float(b), own_term=float(c), own_term_with_strength=float(c2), strength_term=float(d2))
    if t.sum() > 0 and t.sum() < len(t):
        w = logistic(Xl, t)
        p0 = 1 / (1 + np.exp(-w[0])); p1 = 1 / (1 + np.exp(-(w[0] + w[2])))
        r.update(share100_own_minus_others_at_mean_panel=float(100 * (p1 - p0)), own_odds_ratio_100=float(np.exp(w[2])))
    else:
        r.update(share100_own_minus_others_at_mean_panel=float("nan"), own_odds_ratio_100=float("nan"))
    return r


def analyse(X, y, wr, iss, judges, wfam):
    n = len(y); fail = np.where(y == 0)[0]
    rate = {v: float(y[wr == v].mean()) for v in set(wr)}
    strength = np.array([rate[v] for v in wr])
    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    out = {"failing_patches": int(len(fail)), "writer_pass_rate": {k: round(v, 3) for k, v in rate.items()}, "judges": {}}
    for k in judges:
        if k not in OWN or OWN[k] not in rate:
            continue
        excl = {k} if k == G else {k, G}
        panel = np.array([np.mean([X[m][i] for m in judges if m not in excl and FAMILY[m] != wfam[wr[i]]])
                          for i in range(n)])
        own = (wr == OWN[k]).astype(float)
        full = fit(fail, X[k], panel, own, strength)
        rng = np.random.default_rng(SEED); B = collections.defaultdict(list)
        for _ in range(BOOT):
            idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
            idx = idx[y[idx] == 0]
            if own[idx].sum() == 0 or own[idx].sum() == len(idx):
                continue
            for kk, v in fit(idx, X[k], panel, own, strength).items():
                B[kk].append(v)
        res = {"own_failing": int(own[fail].sum()), "other_failing": int(len(fail) - own[fail].sum())}
        for kk, v in full.items():
            lo, hi = (np.nanpercentile(B[kk], 2.5), np.nanpercentile(B[kk], 97.5)) if B[kk] else (np.nan, np.nan)
            res[kk] = [round(v, 2), round(float(lo), 2), round(float(hi), 2)]
        out["judges"][k] = res
    return out


def main():
    res = {"model": "score_J = a + b*(panel_J - mean) + c*own_J on failing patches; values are [estimate, lo95, hi95]",
           "boot": BOOT, "seed": SEED}
    pids, X, y, wr, iss, _ = load(J9, ["main-a", "main-b"])
    res["held-out"] = analyse(X, y, wr, iss, J9, WRITER_FAMILY)
    X, y, wr, iss = load_rows(os.path.join(HERE, "..", "data", "public", "third-party-lite", "patches.jsonl"), "lite", J7)
    res["swe-bench-lite"] = analyse(X, y, wr, iss, J7, LITE_WRITERS)
    X, y, wr, iss = load_rows(os.path.join(HERE, "..", "data", "livecodebench-pilot", "judging", "programs.jsonl"), "lcb", J6)
    res["livecodebench"] = analyse(X, y, wr, iss, J6, LCB_WRITERS)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
