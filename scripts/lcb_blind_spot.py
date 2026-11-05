#!/usr/bin/env python3
"""Shared blind spot on LiveCodeBench (spec/lcb-sweep-blind-spot.md). From scripts/:
python3 lcb_blind_spot.py > derived/lcb_blind_spot_2026-11-03.json"""
import json, os

import numpy as np

import lcb_sweep_analysis as A

JUDGES = ["gemma-4-31b", "gemma-4-12b", "gemma-4-26b-a4b", "gpt-oss-20b", "olmo-3.1-32b", "nemotron-nano-9b-v2",
          "seed-oss-36b"]


def main():
    ids = sorted(set(json.load(open(os.path.join(A.ROOT, "data", "livecodebench-pilot", "judging", "sweep_ids.json")))))
    old = [json.loads(l) for l in open(A.PROGRAMS)]
    q = A.scores(A.QWEN_OLD); q.update(A.scores(os.path.join(A.D, "scores_qwen3-32b-local.jsonl")))
    passed, S, own = {}, {}, {}  # per judge: problem -> 0/1; pid -> score; own failing pids
    for m in JUDGES:
        if m == "gemma-4-31b":
            g = {}
            for r in old:
                if r["writer"] == m and r["iid"] in ids:
                    g[r["iid"]] = max(g.get(r["iid"], 0), r["y"])
            S[m] = A.scores(os.path.join(A.HERE, "derived", "lcb_gemma4-31b.jsonl"))
            own[m] = {r["pid"]: r["iid"] for r in old if r["writer"] == m and r["y"] == 0}
        else:
            ev = json.load(open(os.path.join(A.D, f"{m}_codegeneration_output_eval_all.json")))
            g = {e["question_id"]: int(bool(e["graded_list"][0])) for e in ev if e["question_id"] in ids}
            S[m] = A.scores(os.path.join(A.D, f"scores_{m}.jsonl"))
            own[m] = {r["pid"]: r["iid"] for r in map(json.loads, open(os.path.join(A.D, f"{m}_p1.jsonl")))
                      if g[r["iid"]] == 0}
        passed[m] = g
    out = {}
    for m in JUDGES:
        fam = m in A.GEMMA_FAMILY
        oth = [r for r in old if r["y"] == 0 and r["iid"] in ids and not (fam and r["writer"] in A.GEMMA_FAMILY)
               and r["writer"] != m and r["pid"] in S[m] and r["pid"] in q]
        o_iid = np.array([r["iid"] for r in oth]); o_E = np.array([S[m][r["pid"]] - q[r["pid"]] for r in oth])
        splitters = [k for k in JUDGES if k != m]
        ow = [(p, i) for p, i in own[m].items() if p in S[m] and p in q and i in ids]
        w_iid = np.array([i for _, i in ow]); w_E = np.array([S[m][p] - q[p] for p, _ in ow])
        probs = np.array(ids)

        def split(k, sel):
            f = np.array([passed[k].get(i, 1) == 0 for i in o_iid[sel]])
            if f.sum() == 0 or (~f).sum() == 0:
                return np.nan
            return o_E[sel][f].mean() - o_E[sel][~f].mean()

        def stats(pick):
            sel = np.concatenate([np.where(o_iid == i)[0] for i in pick])
            own_split = split(m, sel)
            plac = np.nanmean([split(k, sel) for k in splitters])
            # measure 2: per problem, own failing E minus mean other failing E, problems with both
            d = []
            for i in pick:
                a = w_E[w_iid == i]; b = o_E[o_iid == i]
                if len(a) and len(b):
                    d.append(a.mean() - b.mean())
            return own_split, own_split - plac, (np.mean(d) if d else np.nan), len(d)

        f_m = np.array([passed[m].get(i, 1) == 0 for i in o_iid])
        n_fail, n_pass = int(f_m.sum()), int((~f_m).sum())
        if min(n_fail, n_pass) < 30:
            out[m] = dict(other_failing_on_own_failed=n_fail, other_failing_on_own_passed=n_pass, result="too few")
            continue
        own_split, effect, m2, n2 = stats(probs)
        rng = np.random.default_rng(0); B = []
        for _ in range(2000):
            B.append(stats(rng.choice(probs, len(probs)))[1:3])
        B = np.array(B)
        ci = lambda c: [round(float(np.nanpercentile(B[:, c], 2.5)), 1), round(float(np.nanpercentile(B[:, c], 97.5)), 1)]
        out[m] = dict(other_failing_on_own_failed=n_fail, other_failing_on_own_passed=n_pass,
                      own_split=round(float(own_split), 1),
                      blind_spot_effect=dict(value=round(float(effect), 1), ci95=ci(0)),
                      own_vs_other_wrong_same_problem=dict(value=round(float(m2), 1), ci95=ci(1), problems=n2))
    tested = [m for m in out if "blind_spot_effect" in out[m]]
    out["summary"] = dict(
        tested=tested,
        blind_spot=[m for m in tested if out[m]["blind_spot_effect"]["ci95"][0] > 0],
        own_beyond=[m for m in tested if out[m]["own_vs_other_wrong_same_problem"]["ci95"][0] > 0])
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
