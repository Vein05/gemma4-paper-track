#!/usr/bin/env python3
"""AUROC (task-clustered bootstrap CI) of cheap end-state predictors of `resolved`.

Direction of each predictor is fixed in advance (score = more likely resolved):
  claims_success_rule (+), last_test_exit0 (+; no test run -> 0), ran_test (+), submitted (+), patch_nonempty (+),
  last_test_summary_pass (+; no test run -> 0),
  patch_chars (-), patch_files (-), patch_added_removed (-), n_agent_steps (-), harness_tool_calls (-).
Usage: python3 probe_baselines.py derived/features_rishav.csv derived/task_sound_flags_dmitriigluzdov.csv [out.csv]
"""
import sys
import numpy as np
import pandas as pd

B = 5000
rng = np.random.default_rng(20261004)


def auroc(y, s):
    y = np.asarray(y); s = np.asarray(s, float)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    cmp = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return cmp / (len(pos) * len(neg))


def cluster_boot(df, col, cluster="task_id"):
    groups = [g for _, g in df.groupby(cluster)]
    n = len(groups)
    ys = [g["resolved"].values for g in groups]
    ss = [g[col].values for g in groups]
    out = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        y = np.concatenate([ys[i] for i in idx]); s = np.concatenate([ss[i] for i in idx])
        a = auroc(y, s)
        if not np.isnan(a):
            out.append(a)
    return np.percentile(out, [2.5, 97.5])


def prep(d):
    d = d.copy()
    for c in ("last_test_exit0", "last_test_summary_pass"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["last_py_exit0"] = pd.to_numeric(d["last_py_exit0"], errors="coerce").fillna(0)
    d["ran_any_check"] = ((d["n_py_cmds"] > 0) | (d["ran_test"] == 1)).astype(int)  # test runner or ad-hoc python script
    d["neg_patch_chars"] = -d["patch_chars"]
    d["neg_patch_files"] = -d["patch_files"]
    d["neg_patch_lines"] = -(d["patch_added"] + d["patch_removed"])
    d["neg_steps"] = -d["n_agent_steps"]
    d["neg_tool_calls"] = -pd.to_numeric(d["harness_tool_calls"])
    return d


PRED = ["claims_success_rule", "last_test_exit0", "last_test_summary_pass", "ran_test", "ran_any_check", "last_py_exit0", "submitted", "patch_nonempty",
        "neg_patch_chars", "neg_patch_files", "neg_patch_lines", "neg_steps", "neg_tool_calls"]


def run(d, label):
    rows = []
    for c in PRED:
        a = auroc(d["resolved"], d[c])
        lo, hi = cluster_boot(d, c)
        rows.append(dict(set=label, predictor=c, n=len(d), n_pos=int(d.resolved.sum()), n_neg=int((1 - d.resolved).sum()),
                         auroc=round(a, 3), ci_lo=round(lo, 3), ci_hi=round(hi, 3)))
    return rows


def loo_logit(d, cols, C=1.0):
    """Leave-one-task-out logistic regression on standardized cheap features; returns out-of-fold scores."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    X = d[cols].astype(float).values
    y = d["resolved"].values
    out = np.zeros(len(d))
    for i in range(len(d)):
        tr = np.arange(len(d)) != i
        sc = StandardScaler().fit(X[tr])
        m = LogisticRegression(C=C, max_iter=1000).fit(sc.transform(X[tr]), y[tr])
        out[i] = m.predict_proba(sc.transform(X[[i]]))[0, 1]
    return out


def main():
    feat, sound = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    d = prep(pd.read_csv(feat))
    s = pd.read_csv(sound)
    d = d.merge(s, on="task_id", how="left")
    sets = {
        "A_all_76": d,
        "B_sound_66": d[d.sound == 1],
        "C_sound_nonempty_patch": d[(d.sound == 1) & (d.patch_nonempty == 1)],
        "D_all_nonempty_patch": d[d.patch_nonempty == 1],
    }
    rows = []
    for k, v in sets.items():
        rows += run(v, k)
    # combined cheap baseline: leave-one-out logistic regression on all cheap features
    combo = ["claims_success_rule", "ran_test", "ran_any_check", "last_test_exit0", "neg_tool_calls", "neg_steps", "neg_patch_chars", "neg_patch_files"]
    for k, v in sets.items():
        v = v.copy()
        v["loo_logit_cheap"] = loo_logit(v, combo)
        a = auroc(v["resolved"], v["loo_logit_cheap"]); lo, hi = cluster_boot(v, "loo_logit_cheap")
        rows.append(dict(set=k, predictor="loo_logit_cheap(8 features)", n=len(v), n_pos=int(v.resolved.sum()), n_neg=int((1 - v.resolved).sum()),
                         auroc=round(a, 3), ci_lo=round(lo, 3), ci_hi=round(hi, 3)))
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))
    if out:
        res.to_csv(out, index=False)


if __name__ == "__main__":
    main()
