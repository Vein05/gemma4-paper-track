#!/usr/bin/env python3
"""Extra trust on Go, Ruby and PHP issues (spec/nonpython-rubber-stamp.md). Reads derived/ml_np-<judge>.jsonl,
data/lab-runs/nonpython/labels.jsonl and the control writers' official labels in data/public/swe-bench-multilingual/. One JSON object on stdout. Intervals: 2,000 resamples of issues, seed 0."""
import collections, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from multilingual_judging import WRITERS, label  # noqa: E402

G = "gemma4-31b"
OUTSIDE = {"glm-4.5": "glm", "qwen35-9b": "qwen", "gpt-oss-20b": "gpt-oss", "llama-4-maverick": "llama"}
FAMILY = {"gemma-4-31b": "gemma", "glm-5": "glm", "kimi-k2-5": "kimi", "deepseek-3-2": "deepseek", "minimax-2-5": "minimax"}
GW = "gemma-4-31b"


def main():
    D = os.path.join(ROOT, "data", "nonpython")
    frozen = json.load(open(os.path.join(D, "issues.json")))
    lang = {i: l for l, v in frozen["languages"].items() for i in v}
    lab = {r["instance_id"]: r.get("resolved") for r in map(json.loads, open(os.path.join(ROOT, "data", "lab-runs", "nonpython", "labels.jsonl")))}
    ref = json.load(open(os.path.join(D, "reference_pass.json")))
    scores = collections.defaultdict(dict); meta = {}
    for j in [G, *OUTSIDE]:
        for r in map(json.loads, open(os.path.join(HERE, "derived", f"ml_np-{j}.jsonl"))):
            if r.get("parsed") is not None:
                scores[r["pid"]][j] = float(r["parsed"]); meta[r["pid"]] = (r["iid"], r["writer"])
    rows = []
    for pid, s in scores.items():
        iid, w = meta[pid]
        if len(s) < 5 or iid not in lang or ref.get(iid) is not True:
            continue
        if w == GW and lab.get(iid) is None:
            continue
        y = int(bool(lab[iid])) if w == GW else 0
        panel = np.mean([v for k, v in s.items() if k != G and OUTSIDE[k] != FAMILY[w]])
        rows.append(dict(iid=iid, writer=w, y=y, g=s[G], panel=panel, e=s[G] - panel,
                         o100=np.mean([s[k] == 100 for k in OUTSIDE if OUTSIDE[k] != FAMILY[w]])))
    issues = sorted({r["iid"] for r in rows}); by = collections.defaultdict(list)
    for r in rows:
        by[r["iid"]].append(r)

    def stats(rs):
        own = [r for r in rs if r["writer"] == GW and r["y"] == 0]; oth = [r for r in rs if r["writer"] != GW]
        out = dict(extra_trust=np.mean([r["e"] for r in own]) - np.mean([r["e"] for r in oth]),
                   stamp_own=np.mean([r["g"] == 100 for r in own]), stamp_controls=np.mean([r["g"] == 100 for r in oth]),
                   outside_stamp_own=np.mean([r["o100"] for r in own]))
        d = collections.defaultdict(lambda: [[], []])
        for r in own:
            d[r["iid"]][0].append(r["e"])
        for r in oth:
            d[r["iid"]][1].append(r["e"])
        pairs = [np.mean(a) - np.mean(b) for a, b in d.values() if a and b]
        out["same_issue"] = float(np.mean(pairs)) if pairs else float("nan")
        for w in WRITERS:
            t = [r["e"] for r in oth if r["writer"] == w]
            out[f"vs_{w}"] = np.mean([r["e"] for r in own]) - np.mean(t) if t else float("nan")
        for l in frozen["languages"]:
            a = [r["e"] for r in own if lang[r["iid"]] == l]; b = [r["e"] for r in oth if lang[r["iid"]] == l]
            out[f"lang_{l}"] = np.mean(a) - np.mean(b) if a and b else float("nan")
        return out

    pt = stats(rows); rng = np.random.default_rng(0); B = collections.defaultdict(list)
    for _ in range(2000):
        for k, v in stats([r for i in rng.choice(issues, len(issues)) for r in by[i]]).items():
            B[k].append(v)
    res = {k: dict(value=round(float(v), 4), ci95=[round(float(np.nanpercentile(B[k], q)), 4) for q in (2.5, 97.5)]) for k, v in pt.items()}
    g = [r for r in rows if r["writer"] == GW]

    def auroc(key):  # how well a score separates Gemma's own passing patches from its failing ones; ties count half
        pos, neg = [r[key] for r in g if r["y"] == 1], [r[key] for r in g if r["y"] == 0]
        return round(float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg])), 3)
    preds = json.load(open(os.path.join(ROOT, "data", "lab-runs", "nonpython", "preds.json")))
    # Share of the issues (reference patch passes) each writer solves, by its official label; Gemma's by ours.
    kept = [i for i in lang if ref.get(i) is True]
    solved = {GW: round(sum(bool(lab.get(i)) for i in kept) / len(kept), 3)}
    att = [json.loads(l) for l in open(os.path.join(ROOT, "data", "public", "swe-bench-multilingual", "attempts.jsonl"))]
    for w in WRITERS:
        rs = {a["instance_id"]: label(a) for a in att if a["writer"].endswith(w) and a["instance_id"] in kept}
        solved[w] = round(sum(bool(rs.get(i)) for i in kept) / len(kept), 3)
    print(json.dumps(dict(issues_run=len(preds), issues_no_patch=sum(not p.get("model_patch") for p in preds.values()),
                          issues=len(issues), gemma_patches=len(g), gemma_passing=sum(r["y"] for r in g),
                          own_failing=sum(r["y"] == 0 for r in g), control_failing=sum(r["writer"] != GW for r in rows),
                          per_language={l: sum(lang[r["iid"]] == l for r in g) for l in frozen["languages"]},
                          stamped_passing=sum(r["y"] == 1 and r["g"] == 100 for r in g),
                          solved=solved,
                          auroc_own=dict(gemma=auroc("g"), outside_judges=auroc("panel")), estimates=res,
                          reading="carries over" if res["extra_trust"]["ci95"][0] > 0 else "does not carry over"), indent=1))


if __name__ == "__main__":
    main()
