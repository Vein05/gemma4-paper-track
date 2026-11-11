#!/usr/bin/env python3
"""Wrong fixes across public models with issue difficulty held fixed (exploratory, 2026-11-11;
spec/hidden-test-and-failure-type-checks.md, part 1).

Same entries, patches and wrong-fix rule as `failure_census.py analyze`. Issue difficulty is how many of the 32 entries
solve the issue. No network.

  python3 wrong_fix_difficulty.py > derived/wrong_fix_difficulty_2026-11-11.json
"""
import collections, json, os, sys

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from failure_census import MIN_REPORTS, ROWS, STRONG, L  # noqa: E402

BANDS = [(0, 0), (1, 7), (8, 15), (16, 23), (24, 32)]
MIN_FAIL = 5  # an entry enters a band's rank correlation with at least this many failing patches that change code
B = 2000


def load():
    rows = L(ROWS)
    issues = sorted({r["iid"] for r in rows})
    reports = collections.Counter(r["entry"] for r in rows if r["report"])
    used = [e for e in sorted({r["entry"] for r in rows}) if reports[e] >= MIN_REPORTS]
    rows = [r for r in rows if r["entry"] in used and r["report"]]
    E, I = {e: k for k, e in enumerate(used)}, {i: k for k, i in enumerate(issues)}
    S, F, W = (np.zeros((len(used), len(issues))) for _ in range(3))
    for r in rows:
        S[E[r["entry"]], I[r["iid"]]] = r["resolved"]
        if r["applied"] and not r["resolved"] and r["patch"] == "code":
            F[E[r["entry"]], I[r["iid"]]] = 1
            W[E[r["entry"]], I[r["iid"]]] = r["other_fail"] == 0
    return used, issues, S, F, W


def main():
    used, issues, S, F, W = load()
    rate = S.mean(1)                      # entry strength: share of all 500 issues solved (as in failure_census)
    nsolve = S.sum(0)                     # issue difficulty: entries that solve it
    strong = np.where(rate >= STRONG)[0]
    mid = np.where((rate >= 0.40) & (rate < 0.60))[0]
    top = np.where(rate >= 0.70)[0]
    rng = np.random.default_rng(0)
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    share = lambda ent, iss: float(W[np.ix_(ent, iss)].sum() / F[np.ix_(ent, iss)].sum()) if F[np.ix_(ent, iss)].sum() else np.nan

    def corr(iss, min_fail=1):
        f = F[np.ix_(strong, iss)].sum(1)
        keep = f >= min_fail
        sh = W[np.ix_(strong, iss)].sum(1)[keep] / f[keep]
        return float(spearmanr(rate[strong][keep], sh).statistic) if keep.sum() >= 3 else np.nan, int(keep.sum())

    def summary(iss, min_fail=1, boot=True):
        iss = np.asarray(iss)
        out = dict(issues=int(len(iss)), failing=int(F[:, iss].sum()), wrong_fixes=int(W[:, iss].sum()),
                   share_all_32=round(share(np.arange(len(used)), iss), 3),
                   entries_40_to_60=dict(failing=int(F[np.ix_(mid, iss)].sum()), share=round(share(mid, iss), 3)),
                   entries_70_or_more=dict(failing=int(F[np.ix_(top, iss)].sum()), share=round(share(top, iss), 3)))
        out["difference_70_minus_40_to_60"] = round(out["entries_70_or_more"]["share"] - out["entries_40_to_60"]["share"], 3)
        r, n = corr(iss, min_fail)
        out["rank_correlation"] = dict(value=round(r, 2), entries=n)
        if boot:
            bs = collections.defaultdict(list)
            for _ in range(B):
                j = iss[rng.integers(0, len(iss), len(iss))]
                bs["all"].append(share(np.arange(len(used)), j))
                bs["diff"].append(share(top, j) - share(mid, j))
                bs["rho"].append(corr(j, min_fail)[0])
            out["share_all_32_ci95"] = ci(bs["all"])
            out["difference_ci95"] = ci(bs["diff"])
            out["rank_correlation"]["ci95"] = [round(x, 2) for x in ci(bs["rho"])]
        return out

    all_i = np.arange(len(issues))
    res = dict(exploratory=True, spec="spec/hidden-test-and-failure-type-checks.md", entries=len(used),
               entries_40_to_60=int(len(mid)), entries_70_or_more=int(len(top)), entries_in_rank_correlation=int(len(strong)))
    res["reproduced"] = summary(all_i, boot=False)
    res["issues_by_entries_solving"] = {str(k): int(v) for k, v in sorted(collections.Counter(nsolve.astype(int)).items())}
    res["without_issues_no_entry_solves"] = summary(np.where(nsolve > 0)[0])
    res["without_issues_3_or_fewer_entries_solve"] = summary(np.where(nsolve > 3)[0])
    res["only_issues_no_entry_solves"] = summary(np.where(nsolve == 0)[0], boot=False)
    res["bands"] = {f"{lo} to {hi} entries solve": summary(np.where((nsolve >= lo) & (nsolve <= hi))[0], MIN_FAIL)
                    for lo, hi in BANDS}

    # (a) within-issue difference: stronger group's share minus weaker group's, on issues both groups fail with code.
    both = np.where((F[mid].sum(0) > 0) & (F[top].sum(0) > 0))[0]
    d_issue = W[np.ix_(top, both)].sum(0) / F[np.ix_(top, both)].sum(0) - W[np.ix_(mid, both)].sum(0) / F[np.ix_(mid, both)].sum(0)
    bd = [d_issue[rng.integers(0, len(both), len(both))].mean() for _ in range(B)]
    res["within_issue_difference"] = dict(issues=int(len(both)), mean=round(float(d_issue.mean()), 3), ci95=ci(bd),
                                          issues_higher_for_stronger=int((d_issue > 0).sum()),
                                          issues_lower_for_stronger=int((d_issue < 0).sum()),
                                          issues_equal=int((d_issue == 0).sum()))

    # (b) linear probability model, wrong fix on share solved (per 10 points), 30 entries, with and without issue effects.
    ent, iss = np.nonzero(F[strong])
    x = rate[strong][ent] * 10
    y = W[strong][ent, iss]

    def slopes(ix):
        xi, yi, gi = x[ix], y[ix], iss[ix]
        plain = np.polyfit(xi, yi, 1)[0]
        # within-issue: demean x and y by issue (resampled copies of one issue count as one group each)
        cnt = np.bincount(gi); mx = np.bincount(gi, xi) / np.maximum(cnt, 1); my = np.bincount(gi, yi) / np.maximum(cnt, 1)
        xd, yd = xi - mx[gi], yi - my[gi]
        fe = float((xd * yd).sum() / (xd * xd).sum())
        return float(plain), fe

    p0, f0 = slopes(np.arange(len(y)))
    rows_of = collections.defaultdict(list)
    for k, i in enumerate(iss):
        rows_of[i].append(k)
    keys = sorted(rows_of)
    bp, bf = [], []
    for _ in range(B):
        pick = rng.integers(0, len(keys), len(keys))
        ix = np.concatenate([rows_of[keys[p]] for p in pick])
        # give each resampled copy its own group id
        gid = np.concatenate([np.full(len(rows_of[keys[p]]), n) for n, p in enumerate(pick)])
        xi, yi = x[ix], y[ix]
        cnt = np.bincount(gid); mx = np.bincount(gid, xi) / cnt; my = np.bincount(gid, yi) / cnt
        xd, yd = xi - mx[gid], yi - my[gid]
        bp.append(np.polyfit(xi, yi, 1)[0]); bf.append((xd * yd).sum() / (xd * xd).sum())
    res["slope_per_10_points_solved"] = dict(patches=int(len(y)), issues=len(keys),
                                             without_issue_effects=dict(value=round(p0, 3), ci95=ci(bp)),
                                             with_issue_effects=dict(value=round(f0, 3), ci95=ci(bf)),
                                             ratio=round(f0 / p0, 2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
