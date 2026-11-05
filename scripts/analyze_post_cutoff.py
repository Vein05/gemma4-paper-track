#!/usr/bin/env python3
"""Before/after training-cutoff test (spec/post-cutoff-test.md).

For each model: the same-conditions summary (selfjudge_matrix.analyze) on the before set and on the after set, and the
change in pair accuracy from before to after per condition with a 95% interval (2,000 bootstrap resamples of issues
within each set).

Usage: python3 analyze_post_cutoff.py gemma4-31b gpt-oss-20b qwen35-9b glm47-flash > derived/post_cutoff_summary_<date>.json
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(__file__))
from selfjudge_matrix import analyze  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def per_issue(path):
    """{issue: {cond: [pair scores]}} with the same rules as selfjudge_matrix.analyze (ties count half)."""
    R = [r for r in map(json.loads, open(path)) if r.get("err") is None]
    P = {(r["cond"], r["pid"]): r["parsed"] for r in R if r["cond"] in ("P0", "P1")}
    C, pairs = collections.defaultdict(dict), {}
    for r in R:
        if r["cond"] in ("C0", "C1"):
            C[(r["cond"], r["iid"], r["pair"])][r["order"]] = (r["parsed"] == r["correct"]) if r["parsed"] else None
            pairs[(r["iid"], r["pair"])] = (r["pos_pid"], r["neg_pid"])
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for (iid, j), (pp, pn) in pairs.items():
        for cond in ("P0", "P1"):
            a, b = P.get((cond, pp)), P.get((cond, pn))
            if a is None or b is None:
                continue
            if cond == "P0":
                a, b = int(a == "PASS"), int(b == "PASS")
            out[iid][cond].append(1.0 if a > b else 0.0 if a < b else 0.5)
        for cond in ("C0", "C1"):
            o = C.get((cond, iid, j), {})
            if o.get("PN") is not None and o.get("NP") is not None:
                out[iid][cond].append((o["PN"] + o["NP"]) / 2)
    return out


def mean(d, ids, cond):
    v = [s for i in ids for s in d[i][cond]]
    return sum(v) / len(v) if v else float("nan")


if __name__ == "__main__":
    res = {}
    for tag in sys.argv[1:]:
        paths = {s: os.path.join(HERE, "derived", f"selfjudge_live-{s}_{tag}.jsonl") for s in ("before", "after")}
        summ = {s: next(iter(analyze([p]).values())) for s, p in paths.items()}
        d = {s: per_issue(p) for s, p in paths.items()}
        ids = {s: sorted(d[s]) for s in d}
        rng = random.Random(0)
        boots = collections.defaultdict(list)
        for _ in range(2000):
            sb = [rng.choice(ids["before"]) for _ in ids["before"]]
            sa = [rng.choice(ids["after"]) for _ in ids["after"]]
            for c in ("P0", "P1", "C0", "C1"):
                boots[c].append(mean(d["after"], sa, c) - mean(d["before"], sb, c))
        change = {c: dict(diff=round(mean(d["after"], ids["after"], c) - mean(d["before"], ids["before"], c), 3),
                          ci_95=(round(sorted(v)[50], 3), round(sorted(v)[1949], 3))) for c, v in boots.items()}
        res[tag] = dict(before=summ["before"], after=summ["after"], after_minus_before=change)
    print(json.dumps(res, indent=1))
