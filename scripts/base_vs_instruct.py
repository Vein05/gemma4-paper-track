#!/usr/bin/env python3
"""spec/base-vs-instruct.md: pretrained vs instruction-tuned Gemma 4 31B on the same plain-text judging prompt.

build:   writes ../data/judge-prompts/base_vs_instruct_examples.jsonl (the four worked examples) and
         ../data/judge-prompts/base_vs_instruct_plain.jsonl (one plain-text prompt per held-out patch, 957 rows, pilot
         rows first, flagged "pilot").
pilot:   format checks only (median digit probability, median log P("100")) from score files.
analyze: leniency, AUROC and descriptive shares from score files; JSON to stdout.

Usage (from scripts/): python base_vs_instruct.py build
                       python base_vs_instruct.py pilot DIR [DIR ...]
                       python base_vs_instruct.py analyze --pre DIR --it DIR [--q4 DIR]
"""
import argparse, json, os, sys

import numpy as np

import fresh_judging as fj
from selection_test import rating_prompt
from selfjudge_matrix import Q_P1

HERE = os.path.dirname(os.path.abspath(__file__))
DP = os.path.join(HERE, "..", "data", "judge-prompts")
NINE = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5", "kimi-k2",
        "llama-4-maverick"]
W, B, SEED = "gemma-4-31b", 2000, 0
SEP = "\n\n=====\n\n"


def held():
    pids, X, y, wr, iss, S = fj.load(NINE, ["main-a", "main-b"])
    return list(pids), np.asarray(y), np.asarray(wr), np.asarray(iss)


def build(a):
    rows = {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(DP, "heldout_p1.jsonl"))}
    pids, y, wr, iss = held()
    held_iids = {r["iid"] for r in rows.values()}
    lite = [json.loads(l) for l in open(os.path.join(HERE, "..", "data", "public", "third-party-lite", "patches.jsonl"))]
    pool = [x for x in lite if not x["writer"].startswith("gemma") and x["iid"] not in held_iids]
    size = lambda x: len(x["issue"]) + len(x["patch"])
    P = sorted((x for x in pool if x["y"] == 1), key=size)[:2]
    F = sorted((x for x in pool if x["y"] == 0), key=size)[:2]
    ex = [P[0], F[0], P[1], F[1]]
    with open(os.path.join(DP, "base_vs_instruct_examples.jsonl"), "w") as fh:
        for x in ex:
            fh.write(json.dumps(dict(pid=x["pid"], iid=x["iid"], writer=x["writer"], y=x["y"])) + "\n")
    system = {r["system"] for r in rows.values()}
    assert len(system) == 1
    system = system.pop()
    shots = SEP.join(rating_prompt(x["iid"], x, Q_P1) + f"\n\nSCORE: {100 if x['y'] else 0}" for x in ex)
    if a.set == "lite":  # spec/pretrained-judge-fix.md: same examples; their issues removed; patches with a written Gemma score
        drop = {x["iid"] for x in ex}
        scored = {r["pid"] for r in map(json.loads, open(os.path.join(HERE, "derived", "lite_gemma4-31b.jsonl")))
                  if r.get("err") is None and r.get("parsed") is not None}
        L = [json.loads(l) for l in open(os.path.join(DP, "lite_p1.jsonl"))]
        assert {r["system"] for r in L} == {system}
        L = [r for r in L if r["iid"] not in drop and r["pid"] in scored]
        with open(os.path.join(DP, "base_vs_instruct_lite_plain.jsonl"), "w") as fh:
            for r in L:
                text = system + "\n\n" + shots + SEP + r["prompt"] + "\n\nSCORE: "
                fh.write(json.dumps(dict(pid=r["pid"], iid=r["iid"], writer=r["writer"], pilot=False, text=text)) + "\n")
        print(json.dumps(dict(rows=len(L), dropped_issues=sorted(drop), own=sum(r["writer"] == W for r in L))))
        return
    # pilot: 10 failing + 10 passing own, 10 + 10 other writers, seed 0
    rng = np.random.default_rng(SEED)
    pilot = set()
    for own in (True, False):
        for lab in (0, 1):
            idx = [i for i in range(len(pids)) if (wr[i] == W) == own and y[i] == lab]
            pilot |= {pids[i] for i in rng.choice(idx, 10, replace=False)}
    order = [p for p in pids if p in pilot] + [p for p in pids if p not in pilot]
    lab_of = dict(zip(pids, y.tolist()))
    with open(os.path.join(DP, "base_vs_instruct_plain.jsonl"), "w") as fh:
        for p in order:
            r = rows[p]
            text = system + "\n\n" + shots + SEP + r["prompt"] + "\n\nSCORE: "
            fh.write(json.dumps(dict(pid=p, iid=r["iid"], writer=r["writer"], pilot=p in pilot, text=text)) + "\n")
    print(json.dumps(dict(examples=[(x["pid"], x["y"], size(x)) for x in ex], rows=len(order), pilot=len(pilot),
                          own_failing=int(((wr == W) & (y == 0)).sum()), labels_known=len(lab_of))))


def read(d):
    return {json.loads(l)["pid"]: json.loads(l) for l in open(os.path.join(d, "plain.jsonl"))}


def pilot(a):
    for d in a.dirs:
        R = read(d)
        pdig = [sum(r["p_digit"]) for r in R.values()]
        lp = [r["logp100"] for r in R.values()]
        print(json.dumps(dict(dir=d, n=len(R), median_p_digit=round(float(np.median(pdig)), 3),
                              min_p_digit=round(float(np.min(pdig)), 3), median_logp100=round(float(np.median(lp)), 3),
                              passes=bool(np.median(pdig) >= 0.5))))


def auroc(s, y):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else float("nan")


def measures(s, y, wr, iss, idx):
    """s: percentile of log P("100") among all 957; idx: resampled positions (issue bootstrap)."""
    s, y, wr, iss = s[idx], y[idx], wr[idx], iss[idx]
    own = wr == W
    diffs = []
    for k in np.unique(iss):
        m = iss == k
        a, b = s[m & own & (y == 0)], s[m & ~own & (y == 0)]
        if len(a) and len(b):
            diffs.append(a.mean() - b.mean())
    return dict(leniency=float(np.mean(diffs)) if diffs else float("nan"), n_issues=len(diffs),
                auroc_own=auroc(s[own], y[own]), auroc_others=auroc(s[~own], y[~own]),
                gap=auroc(s[~own], y[~own]) - auroc(s[own], y[own]))


def analyze(a):
    pids, y, wr, iss = held()
    models = {"pretrained": a.pre, "instruct": a.it}
    if a.q4:
        models["instruct_4bit"] = a.q4
    R = {k: read(d) for k, d in models.items()}
    keep = [i for i, p in enumerate(pids) if all(p in R[k] for k in R)]
    pids = [pids[i] for i in keep]; y, wr, iss = y[keep], wr[keep], iss[keep]
    lp = {k: np.array([R[k][p]["logp100"] for p in pids]) for k in R}
    pct = {k: 100 * (np.argsort(np.argsort(v)) + 0.5) / len(v) for k, v in lp.items()}
    full = np.arange(len(pids))
    out = dict(n=len(pids), left_out=957 - len(pids), own_failing=int(((wr == W) & (y == 0)).sum()))
    point = {k: measures(pct[k], y, wr, iss, full) for k in R}
    ui = np.unique(iss); pos = {k: np.where(iss == k)[0] for k in ui}
    rng = np.random.default_rng(SEED)
    boot = {k: [] for k in R}; bd = []; bq = []
    for _ in range(B):
        idx = np.concatenate([pos[k] for k in rng.choice(ui, len(ui))])
        m = {k: measures(pct[k], y, wr, iss, idx) for k in R}
        for k in R:
            boot[k].append(m[k])
        bd.append(m["instruct"]["leniency"] - m["pretrained"]["leniency"])
        if "instruct_4bit" in R:
            bq.append(m["instruct_4bit"]["leniency"] - m["instruct"]["leniency"])
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]
    for k in R:
        out[k] = {f: (round(point[k][f], 3) if isinstance(point[k][f], float) else point[k][f]) for f in point[k]}
        for f in ("leniency", "auroc_own", "auroc_others", "gap"):
            out[k][f + "_ci"] = ci([b[f] for b in boot[k]])
        own_f, oth_f = (wr == W) & (y == 0), (wr != W) & (y == 0)
        out[k]["share_p100_above_half_own_failing"] = round(float((np.exp(lp[k][own_f]) > 0.5).mean()), 3)
        out[k]["share_p100_above_half_other_failing"] = round(float((np.exp(lp[k][oth_f]) > 0.5).mean()), 3)
    D = point["instruct"]["leniency"] - point["pretrained"]["leniency"]
    out["D_instruct_minus_pretrained"] = round(D, 3); out["D_ci"] = ci(bd)
    if bq:
        out["instruct_4bit_minus_bf16_leniency"] = round(point["instruct_4bit"]["leniency"] - point["instruct"]["leniency"], 3)
        out["instruct_4bit_minus_bf16_ci"] = ci(bq)
    lo = lambda v: v[0] > 0
    Dci, Lp = out["D_ci"], out["pretrained"]["leniency_ci"]
    Li = out["instruct"]["leniency_ci"]
    if Dci[1] < 0:
        verdict = "post-training reduces it"
    elif lo(Dci) and Lp[0] <= 0 <= Lp[1]:
        verdict = "post-training creates it"
    elif lo(Dci) and lo(Lp):
        verdict = "post-training adds to it"
    elif Dci[0] <= 0 <= Dci[1] and lo(Lp) and lo(Li):
        verdict = "present before post-training"
    else:
        verdict = "inconclusive"
    out["reading"] = verdict
    out["format_kept_effect"] = bool(lo(Li))
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("build"); p.add_argument("--set", choices=["heldout", "lite"], default="heldout")
    p = sp.add_parser("pilot"); p.add_argument("dirs", nargs="+")
    p = sp.add_parser("analyze"); p.add_argument("--pre", required=True); p.add_argument("--it", required=True)
    p.add_argument("--q4", default="")
    a = ap.parse_args()
    {"build": build, "pilot": pilot, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
