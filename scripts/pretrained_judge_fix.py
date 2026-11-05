#!/usr/bin/env python3
"""spec/pretrained-judge-fix.md: does scoring Gemma's patches with the pretrained Gemma remove the extra trust and keep
the ranking? JSON to stdout.

Usage (from scripts/):
  python pretrained_judge_fix.py --set lite --pre DIR --it DIR      (confirmation)
  python pretrained_judge_fix.py --set heldout --pre DIR --it DIR   (development table, already seen)
DIR holds plain.jsonl from probe_extract.py plain.
"""
import argparse, json, os

import numpy as np
from sklearn.metrics import roc_auc_score

from base_vs_instruct import held, measures, W, B, SEED

HERE = os.path.dirname(os.path.abspath(__file__))


def rd(d):
    return {json.loads(l)["pid"]: json.loads(l)["logp100"] for l in open(os.path.join(d, "plain.jsonl")) if "logp100" in l}


def lite():
    P = {r["pid"]: r for r in map(json.loads, open(os.path.join(HERE, "..", "data", "public", "third-party-lite",
                                                                  "patches.jsonl")))}
    g = {r["pid"]: r["parsed"] for r in map(json.loads, open(os.path.join(HERE, "derived", "lite_gemma4-31b.jsonl")))
         if r.get("err") is None and r.get("parsed") is not None}
    pids = sorted(p for p in g if p in P)
    return pids, np.array([P[p]["y"] for p in pids]), np.array([P[p]["writer"] for p in pids]), \
        np.array([P[p]["iid"] for p in pids]), np.array([g[p] for p in pids], float)


def heldout():
    import fresh_judging as fj
    from base_vs_instruct import NINE
    pids, X, y, wr, iss, _ = fj.load(NINE, ["main-a", "main-b"])
    return list(pids), np.asarray(y), np.asarray(wr), np.asarray(iss), X["gemma4-31b"]


def auc(s, y):
    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else float("nan")


def approval(appr, y, own):
    f, p = own & (y == 0), own & (y == 1)
    return dict(own_failing=float(appr[f].mean()), own_passing=float(appr[p].mean()),
                precision_own=float(y[own & appr].mean()) if (own & appr).any() else float("nan"),
                other_failing=float(appr[~own & (y == 0)].mean()), other_passing=float(appr[~own & (y == 1)].mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["lite", "heldout"], required=True)
    ap.add_argument("--pre", required=True); ap.add_argument("--it", required=True)
    a = ap.parse_args()
    pids, y, wr, iss, wscore = lite() if a.set == "lite" else heldout()
    pre, it = rd(a.pre), rd(a.it)
    keep = [i for i, p in enumerate(pids) if p in pre and p in it]
    pids = [pids[i] for i in keep]; y, wr, iss, wscore = y[keep], wr[keep], iss[keep], wscore[keep]
    lp = dict(pretrained=np.array([pre[p] for p in pids]), instruct=np.array([it[p] for p in pids]))
    pct = {k: 100 * (np.argsort(np.argsort(v)) + 0.5) / len(v) for k, v in lp.items()}
    own = wr == W
    out = dict(set=a.set, n=len(pids), own=int(own.sum()), own_failing=int((own & (y == 0)).sum()),
               issues=len(np.unique(iss)))
    full = np.arange(len(pids))

    def stats(idx):
        m = {k: measures(pct[k], y, wr, iss, idx)["leniency"] for k in pct}
        o = idx[own[idx]]
        aw = auc(wscore[o], y[o])
        return dict(L_pre=m["pretrained"], L_it=m["instruct"], D=m["instruct"] - m["pretrained"],
                    auroc_own_written=aw, auroc_own_pre=auc(lp["pretrained"][o], y[o]),
                    auroc_own_it=auc(lp["instruct"][o], y[o]),
                    diff_pre_minus_written=auc(lp["pretrained"][o], y[o]) - aw,
                    diff_it_minus_written=auc(lp["instruct"][o], y[o]) - aw,
                    diff_pre_minus_it=auc(lp["pretrained"][o], y[o]) - auc(lp["instruct"][o], y[o]))  # addendum 1

    pt = stats(full)
    ui = np.unique(iss); pos = {k: np.where(iss == k)[0] for k in ui}
    rng = np.random.default_rng(SEED)
    bs = [stats(np.concatenate([pos[k] for k in rng.choice(ui, len(ui))])) for _ in range(B)]
    for k, v in pt.items():
        out[k] = round(v, 3)
        out[k + "_ci"] = [round(float(np.nanpercentile([b[k] for b in bs], q)), 3) for q in (2.5, 97.5)]
    out["approval"] = {name: {f: round(v, 3) for f, v in approval(appr, y, own).items()} for name, appr in (
        ("paper_written_100", wscore >= 100), ("instruct_p100_above_half", np.exp(lp["instruct"]) > 0.5),
        ("pretrained_p100_above_half", np.exp(lp["pretrained"]) > 0.5))}
    # addendum 1: failing patches approved at matched approval of passing patches (Gemma's own patches)
    Pm, Fm = own & (y == 1), own & (y == 0)
    mt = {"paper_written_100": dict(passing=round(float((wscore[Pm] >= 100).mean()), 3),
                                    failing=round(float((wscore[Fm] >= 100).mean()), 3))}
    for name, s in (("instruct_p100", lp["instruct"]), ("pretrained_p100", lp["pretrained"])):
        mt[name] = {}
        for share in (0.85, 0.70, 0.58):
            t = np.quantile(s[Pm], 1 - share)
            mt[name][f"{share:.2f}"] = dict(passing=round(float((s[Pm] >= t).mean()), 3),
                                           failing=round(float((s[Fm] >= t).mean()), 3))
    out["matched_approval"] = mt
    Lp, Dc, dd = out["L_pre_ci"], out["D_ci"], out["diff_pre_minus_written_ci"]
    if Lp[0] > 0 or Dc[0] <= 0:
        v = "not confirmed"
    elif dd[0] > 0:
        v = "fix confirmed, better ranking too"
    elif dd[0] > -0.05:
        v = "fix confirmed"
    else:
        v = "bias removed, ranking lost"
    out["reading"] = v
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
