#!/usr/bin/env python3
"""Summarise quick-check judge runs (public data): verdict and forced-choice metrics per judge,
with 2,000 issue-clustered bootstrap resamples.

Usage: python3 analyze_xjudge.py NAME=verdict_file[,afc_file] ...
"""
import collections, itertools, json, random, sys


def load(paths):
    rows = []
    for p in paths:
        rows += [json.loads(l) for l in open(p) if l.strip()]
    V = [r for r in rows if r["kind"] == "verdict" and r.get("text") in ("PASS", "FAIL")]
    A = [r for r in rows if r["kind"] == "afc" and r.get("text") in ("A", "B")]
    nv = sum(r["kind"] == "verdict" for r in rows); na = sum(r["kind"] == "afc" for r in rows)
    return V, A, nv, na, sum(r.get("cost") or 0 for r in rows)


def metrics(V, A, iids):
    cnt = collections.Counter(iids)
    P = {}
    for r in V:
        if r["rep"] == 1:
            P[r["pid"]] = (r["text"] == "PASS", r["y"], r["iid"])
    rows = [(v, y) for v, y, i in P.values() for _ in range(cnt[i])]
    pos = [v for v, y in rows if y == 1]; neg = [v for v, y in rows if y == 0]
    sens = sum(pos) / len(pos) if pos else float("nan"); spec = 1 - sum(neg) / len(neg) if neg else float("nan")
    byi = collections.defaultdict(lambda: ([], []))
    for v, y, i in P.values():
        byi[i][0 if y else 1].append(v)
    s = n = 0
    for i, k in cnt.items():
        for a, b in itertools.product(*byi[i]):
            s += k * (1 if (a and not b) else 0 if (b and not a) else .5); n += k
    arows = [r for r in A for _ in range(cnt[r["iid"]])]
    afc = sum(r["text"] == r["correct"] for r in arows) / len(arows) if arows else float("nan")
    pairs = collections.defaultdict(dict)
    for r in A:
        if cnt[r["iid"]]:
            pairs[(r["iid"], r["pair"])][r["order"]] = (r["text"], cnt[r["iid"]])
    both = [(d["PN"][0], d["NP"][0], d["PN"][1]) for d in pairs.values() if len(d) == 2]
    cb = sum(k for a, b, k in both if a == "A" and b == "B") / max(1, sum(k for _, _, k in both))
    return dict(sens=sens, spec=spec, bal=(sens + spec) / 2, within=s / n if n else float("nan"), afc=afc, afc_both=cb,
                pA=sum(r["text"] == "A" for r in arows) / len(arows) if arows else float("nan"))


def main():
    for arg in sys.argv[1:]:
        name, files = arg.split("=")
        V, A, nv, na, cost = load(files.split(","))
        iids = sorted({r["iid"] for r in V} | {r["iid"] for r in A})
        point = metrics(V, A, iids)
        rng = random.Random(0); boots = collections.defaultdict(list)
        for _ in range(2000):
            m = metrics(V, A, [rng.choice(iids) for _ in iids])
            for k, v in m.items():
                boots[k].append(v)
        ci = {k: (sorted(v)[50], sorted(v)[1949]) for k, v in boots.items()}
        f = lambda k: f"{point[k]:.2f} [{ci[k][0]:.2f},{ci[k][1]:.2f}]"
        print(f"{name:<12} parsed verdict {len(V)}/{nv} afc {len(A)}/{na} cost ${cost:.3f} | sens {point['sens']:.2f} spec {point['spec']:.2f} "
              f"| bal {f('bal')} | within {f('within')} | AFC {f('afc')} | AFC both-orders {point['afc_both']:.2f} | P(A) {point['pA']:.2f}")


if __name__ == "__main__":
    main()
