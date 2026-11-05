#!/usr/bin/env python3
"""Spec addendum 3 (spec/judge-as-actor.md): gpt-oss-20b with a shell against gpt-oss-20b reading, on the 133 patches
Gemma 4 31B scored 100 as a reader. Shell scores pooled from the pilot, the rerun of errored runs and the forced final
answers; reading scores local (vLLM) and OpenRouter. 2,000 issue resamples, seed 0 (one patch per issue).

  python3 judge_actor_complete.py > derived/judge_as_actor_complete_2026-11-04.json
"""
import json, os, random

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "lab-runs", "judge-as-actor")


def rows(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def auroc(y, s):
    P = [v for t, v in zip(y, s) if t == 1]; N = [v for t, v in zip(y, s) if t == 0]
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


def ranks(x):
    o = sorted(range(len(x)), key=lambda i: x[i]); r = [0.0] * len(x); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and x[o[j + 1]] == x[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def boot(y, fn, B=2000):
    rng = random.Random(0); n = len(y); v = []
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        if 0 < sum(y[i] for i in idx) < n:
            v.append(fn(idx))
    v.sort()
    return [round(v[int(0.025 * len(v))], 3), round(v[int(0.975 * len(v)) - 1], 3)]


def compare(pids, y, a, r):
    """AUROC of a, of r, and a minus r, with intervals, on the given patches."""
    Y = [y[p] for p in pids]; A = [a[p] for p in pids]; R = [r[p] for p in pids]
    sub = lambda idx, s: auroc([Y[i] for i in idx], [s[i] for i in idx])
    C = [u + v for u, v in zip(ranks(A), ranks(R))]
    return dict(n=len(pids), n_pass=sum(Y),
                shell=dict(value=round(auroc(Y, A), 3), ci=boot(Y, lambda i: sub(i, A))),
                reading=dict(value=round(auroc(Y, R), 3), ci=boot(Y, lambda i: sub(i, R))),
                shell_minus_reading=dict(value=round(auroc(Y, A) - auroc(Y, R), 3), ci=boot(Y, lambda i: sub(i, A) - sub(i, R))),
                rank_sum_minus_reading=dict(value=round(auroc(Y, C) - auroc(Y, R), 3),
                                            ci=boot(Y, lambda i: auroc([Y[k] for k in i], [u + v for u, v in zip(ranks([A[k] for k in i]), ranks([R[k] for k in i]))]) - sub(i, R))))


def main():
    jobs = {j["pid"]: j for j in rows(os.path.join(D, "jobs.jsonl")) if j["set"] == "own" and j["stamped"]}
    y = {p: j["y"] for p, j in jobs.items()}
    pilot = {r["pid"]: r for r in rows(os.path.join(D, "gptoss", "runs.jsonl"))}
    rerun = {r["pid"]: r for r in rows(os.path.join(D, "gptoss-rerun", "runs.jsonl"))}
    final = {r["pid"]: r for r in rows(os.path.join(D, "gptoss-final", "runs.jsonl"))}
    shell, source = {}, {}
    for name, d in (("pilot", pilot), ("rerun", rerun), ("forced_final", final)):
        for p, r in d.items():
            if p in jobs and r.get("score") is not None and p not in shell:
                shell[p], source[p] = r["score"], name
    local = {}
    for r in rows(os.path.join(D, "gptoss-reader", "fresh_gpt-oss-20b-local.jsonl")):
        if r["pid"] in jobs and r.get("parsed") is not None:
            local[r["pid"]] = r["parsed"]  # later rows (the --redo-unparsed pass) replace earlier ones
    openrouter = {p: j["reader"]["gpt-oss-20b"] for p, j in jobs.items()}
    out = dict(
        counts=dict(patches=len(jobs), shell_scored=len(shell), by_source={s: list(source.values()).count(s) for s in ("pilot", "rerun", "forced_final")},
                    unscored=len(jobs) - len(shell), local_reading_scored=len(local),
                    rerun_status={r["status"]: sum(x["status"] == r["status"] for x in rerun.values()) for r in rerun.values()},
                    final_status={r["status"]: sum(x["status"] == r["status"] for x in final.values()) for r in final.values()}),
        primary_pooled_vs_local=compare(sorted(p for p in shell if p in local), y, shell, local),
        without_forced_vs_local=compare(sorted(p for p in shell if p in local and source[p] != "forced_final"), y, shell, local),
        pooled_vs_openrouter=compare(sorted(shell), y, shell, openrouter),
        local_vs_openrouter_reading_all=dict(local=round(auroc([y[p] for p in sorted(local)], [local[p] for p in sorted(local)]), 3),
                                             openrouter_same=round(auroc([y[p] for p in sorted(local)], [openrouter[p] for p in sorted(local)]), 3)),
    )
    F = [p for p in shell if source[p] == "forced_final"]
    if F:
        appr = lambda lab, cut: [shell[p] >= cut for p in F if y[p] == lab]
        out["forced_final_alone"] = dict(n=len(F), n_pass=sum(y[p] for p in F),
                                         approval_100=dict(fail=round(sum(appr(0, 100)) / max(1, len(appr(0, 100))), 3), passing=round(sum(appr(1, 100)) / max(1, len(appr(1, 100))), 3)),
                                         approval_90=dict(fail=round(sum(appr(0, 90)) / max(1, len(appr(0, 90))), 3), passing=round(sum(appr(1, 90)) / max(1, len(appr(1, 90))), 3)),
                                         auroc=round(auroc([y[p] for p in F], [shell[p] for p in F]), 3) if 0 < sum(y[p] for p in F) < len(F) else None)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
