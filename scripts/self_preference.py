#!/usr/bin/env python3
"""Self-preference check (spec/own-attempts-test.md, addendum).

exploratory: the unplanned first look. For each patch rated by all four judges (reasoning-first score, temperature 0),
  Gemma's score minus the mean of the other three; Gemma 4's own patches (derived/selection-own_*.jsonl) vs SWE-agent
  patches (derived/selfjudge_*.jsonl), different issues.
run: one reasoning-first rating per judge for every usable Gemma 4 patch on the 50 SWE-bench Verified Mini issues and
  every patch of the six control writers on the same issues (data/public/swe-bench-verified-mini-control/). Ratings
  already in derived/selection-own_<tag>.jsonl are reused. Rows: derived/selfpref_<tag>.jsonl.
analyze: the measures fixed in the addendum (same 50 issues, writer = Gemma vs control writers; family checks).

Usage:
  python3 self_preference.py exploratory > derived/self_preference_<date>.json
  python3 self_preference.py run --model M --tag T [--workers 6] [--reasoning --max-tokens 6000]
  python3 self_preference.py analyze > derived/self_preference_control_<date>.json
"""
import argparse, collections, concurrent.futures, json, os, random, sys

sys.path.insert(0, os.path.dirname(__file__))
from api_quickcheck import strip_tests  # noqa: E402
from live_data import MAX_CHARS  # noqa: E402
from selection_test import pid_of, rating_prompt  # noqa: E402
from selfjudge_matrix import Q_P1, call, parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "public")
TAGS = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash"]
FAMILY = {"gpt-oss-20b": "gpt-oss-120b", "glm47-flash": "glm-4.5", "qwen35-9b": "qwen3-coder"}


def boot_ci(a, b, n=2000, seed=0):
    """a, b: {issue: [values]}. Mean(a) - mean(b) and a 95% interval, resampling issues within each."""
    m = lambda g, ids: (lambda v: sum(v) / len(v) if v else float("nan"))([x for i in ids for x in g[i]])
    ia, ib = sorted(a), sorted(b)
    rng = random.Random(seed)
    d = sorted(m(a, [rng.choice(ia) for _ in ia]) - m(b, [rng.choice(ib) for _ in ib]) for _ in range(n))
    return round(m(a, ia), 1), round(m(b, ib), 1), round(m(a, ia) - m(b, ib), 1), (round(d[int(.025 * n)], 1), round(d[int(.975 * n)], 1))


def exploratory():
    def scores(fmt):
        S = {}
        for t in TAGS:
            for l in open(os.path.join(HERE, "derived", fmt.format(t))):
                r = json.loads(l)
                if r.get("cond") == "P1" and r.get("err") is None and r.get("parsed") is not None:
                    S.setdefault((r["iid"], r["pid"], r["y"]), {})[t] = r["parsed"]
        gap = collections.defaultdict(lambda: collections.defaultdict(list))
        for (iid, pid, y), s in S.items():
            if len(s) == 4:
                gap[y][iid].append(s["gemma4-31b"] - sum(s[t] for t in TAGS[1:]) / 3)
        return gap
    own, other = scores("selection-own_{}.jsonl"), scores("selfjudge_{}.jsonl")
    out = {}
    for y, name in ((0, "failing"), (1, "passing")):
        a, b, d, ci = boot_ci(own[y], other[y])
        out[name] = dict(gemma_minus_others_own=a, gemma_minus_others_swe_agent=b, difference=d, ci_95=ci,
                         n_own=sum(map(len, own[y].values())), n_swe_agent=sum(map(len, other[y].values())))
    return out


def patches():
    """All usable patches on the 50 issues: Gemma 4's own (writer 'gemma-4-31b') and the six control writers."""
    import pyarrow.parquet as pq
    issues = {r["instance_id"]: r["problem_statement"] for r in pq.read_table(
        os.path.join(DATA, "gemma4-own-attempts", "swe-bench-verified-mini.parquet"), columns=["instance_id", "problem_statement"]).to_pylist()}
    out = {}
    for l in open(os.path.join(DATA, "gemma4-own-attempts", "attempts.jsonl")):
        a = json.loads(l)
        p = strip_tests(a["patch"]) if a.get("usable") else ""
        if p and len(p) <= MAX_CHARS:
            x = dict(iid=a["instance_id"], y=int(a["resolved"]), patch=p, issue=issues[a["instance_id"]], writer="gemma-4-31b")
            out.setdefault(pid_of(a["instance_id"], x), x)
    for l in open(os.path.join(DATA, "swe-bench-verified-mini-control", "attempts.jsonl")):
        a = json.loads(l)
        p = strip_tests(a["patch"] or "")
        if p and len(p) <= MAX_CHARS and a["resolved"] is not None:
            w = a["writer"].split("_", 2)[-1].lower()
            w = next((k for k in ("gpt-oss-120b", "glm-4.5", "qwen3-coder", "llama-4-maverick", "kimi-k2", "devstral") if k in w), w)
            x = dict(iid=a["instance_id"], y=int(a["resolved"]), patch=p, issue=issues[a["instance_id"]], writer=w)
            out.setdefault(pid_of(a["instance_id"], x), x)
    return out


def run(a):
    P = patches()
    out = os.path.join(HERE, "derived", f"selfpref_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    old = {}
    sel = os.path.join(HERE, "derived", f"selection-own_{a.tag}.jsonl")
    for l in open(sel) if os.path.exists(sel) else []:
        r = json.loads(l)
        if r.get("cond") == "P1" and r.get("err") is None:
            old[r["pid"]] = r
    jobs, reused = [], []
    for pid, x in sorted(P.items()):
        if pid in done:
            continue
        meta = dict(cond="P1", iid=x["iid"], pid=pid, y=x["y"], writer=x["writer"], model=a.model)
        if pid in old:
            reused.append(dict(meta, parsed=old[pid]["parsed"], provider=old[pid].get("provider"), cost=0.0, err=None, reused=True))
        else:
            jobs.append((meta, rating_prompt(x["iid"], x, Q_P1)))
    print(f"{a.model}: patches {len(P)}, reused {len(reused)}, new calls {len(jobs)}", flush=True)
    with open(out, "a") as fh:
        for r in reused:
            fh.write(json.dumps(r) + "\n")
        with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(call, a.model, pr, a.max_tokens, reasoning=a.reasoning): meta for meta, pr in jobs}
            for f in concurrent.futures.as_completed(futs):
                row = dict(futs[f], reused=False); row.update(f.result()); row["parsed"] = parse("P1", row["content"])
                fh.write(json.dumps(row) + "\n"); fh.flush()


def analyze():
    S = collections.defaultdict(dict)  # pid -> {tag: score}
    meta = {}
    for t in TAGS:
        for l in open(os.path.join(HERE, "derived", f"selfpref_{t}.jsonl")):
            r = json.loads(l)
            if r.get("err") is None and r.get("parsed") is not None:
                S[r["pid"]][t] = r["parsed"]; meta[r["pid"]] = (r["iid"], r["y"], r["writer"])
    full = {p: s for p, s in S.items() if len(s) == 4}

    def gap(judge, keep):
        g = {0: collections.defaultdict(list), 1: collections.defaultdict(list)}
        for p, s in full.items():
            iid, y, w = meta[p]
            if keep(w):
                g[y][iid].append(s[judge] - sum(s[t] for t in TAGS if t != judge) / 3)
        return g

    out = dict(patches_rated_by_all=len(full), patches_by_writer=collections.Counter(meta[p][2] for p in full),
               unparsed_or_missing=len(S) - len(full))
    controls = {"gpt-oss-120b", "glm-4.5", "qwen3-coder", "llama-4-maverick", "kimi-k2", "devstral"}
    own, ctrl = gap("gemma4-31b", lambda w: w == "gemma-4-31b"), gap("gemma4-31b", lambda w: w in controls)
    for y, name in ((0, "failing"), (1, "passing")):
        a, b, d, ci = boot_ci(own[y], ctrl[y])
        out[f"gemma_{name}"] = dict(own=a, control_writers=b, difference=d, ci_95=ci,
                                    n_own=sum(map(len, own[y].values())), n_control=sum(map(len, ctrl[y].values())))
    for judge, fam in FAMILY.items():
        f_, o_ = gap(judge, lambda w: w == fam), gap(judge, lambda w: w in controls - {fam})
        for y, name in ((0, "failing"), (1, "passing")):
            a, b, d, ci = boot_ci(f_[y], o_[y])
            out[f"family_{judge}_on_{fam}_{name}"] = dict(family=a, other_control_writers=b, difference=d, ci_95=ci,
                                                          n_family=sum(map(len, f_[y].values())))
    # mean raw score per judge, writer group and label (descriptive)
    raw = collections.defaultdict(list)
    for p, s in full.items():
        iid, y, w = meta[p]
        for t in TAGS:
            raw[f"{t}|{'gemma' if w == 'gemma-4-31b' else 'control'}|{y}"].append(s[t])
    out["mean_score"] = {k: round(sum(v) / len(v), 1) for k, v in sorted(raw.items())}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("exploratory"); sp.add_parser("analyze")
    r = sp.add_parser("run"); r.add_argument("--model", required=True); r.add_argument("--tag", required=True)
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--redo-unparsed", action="store_true", help="ask again for patches whose rating did not parse")
    r.add_argument("--reasoning", action="store_true", help="switch the model's own reasoning on (default off)")
    r.add_argument("--max-tokens", type=int, default=3000)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a)
    else:
        print(json.dumps(exploratory() if a.cmd == "exploratory" else analyze(), indent=1))
