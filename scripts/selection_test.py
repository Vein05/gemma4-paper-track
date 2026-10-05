#!/usr/bin/env python3
"""Selection test (spec/selection-test.md): choose one patch out of a pool of 4 (1 passing, 3 failing) by pointwise
rating or by pairwise comparison, and count model calls.

Uses the prompts, API call and answer parser of selfjudge_matrix.py. Temperature-0 ratings already collected for the
same model, patch and prompt in derived/selfjudge_<tag>.jsonl are reused (marked reused=True); comparisons already
collected for the same ordered pair are reused too.

Usage:
  python3 selection_test.py run --cache DIR --model M --tag T [--workers 8]
  python3 selection_test.py analyze T1 [T2 ...]
  python3 selection_test.py run --own ../data/public/gemma4-own-attempts --model M --tag T   (spec/own-attempts-test.md)
  python3 selection_test.py analyze --own T1 [T2 ...]
"""
import argparse, collections, concurrent.futures, hashlib, itertools, json, os, random, sys

sys.path.insert(0, os.path.dirname(__file__))
from api_quickcheck import load, repo_of  # noqa: E402
from selfjudge_matrix import Q_C0, Q_C1, Q_P0, Q_P1, call, parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
POOL_SEED, LOAD_SEED, N_FAIL, N_SAMPLES, SAMPLE_TEMP = 20261005, 20261004, 3, 3, 0.7
TOK_ANSWER, TOK_REASON = 8, 3000


def pid_of(iid, x):
    return f"{iid}|{x['y']}|{hashlib.md5(x['patch'].encode()).hexdigest()[:8]}"


def pools(cache):
    sel = load(cache, 10, LOAD_SEED)
    rng = random.Random(POOL_SEED)
    out = {}
    for iid, (pos, neg) in sorted(sel.items()):
        if len(neg) < N_FAIL:
            continue
        members = [rng.choice(pos)] + rng.sample(neg, N_FAIL)
        rng.shuffle(members)
        out[iid] = members
    return out


def pools_own(data_dir):
    """Own-attempts pools (spec/own-attempts-test.md): all unique usable Gemma 4 patches per issue, for issues with at
    least one passing and one failing patch. Pool size varies (2-6)."""
    import pyarrow.parquet as pq
    from api_quickcheck import strip_tests
    from live_data import MAX_CHARS
    issues = {r["instance_id"]: r["problem_statement"] for r in
              pq.read_table(os.path.join(data_dir, "swe-bench-verified-mini.parquet"), columns=["instance_id", "problem_statement"]).to_pylist()}
    by = collections.defaultdict(dict)
    for l in open(os.path.join(data_dir, "attempts.jsonl")):
        a = json.loads(l)
        p = strip_tests(a["patch"]) if a.get("usable") else ""
        if p and len(p) <= MAX_CHARS:
            by[a["instance_id"]].setdefault((int(a["resolved"]), p), dict(iid=a["instance_id"], y=int(a["resolved"]), patch=p,
                                                                          issue=issues[a["instance_id"]], run=a["run"]))
    rng = random.Random(POOL_SEED)
    out = {}
    for iid, uniq in sorted(by.items()):
        members = list(uniq.values())
        if {x["y"] for x in members} == {0, 1}:
            rng.shuffle(members)
            out[iid] = members
    return out


def head(iid, issue):
    return f"A user reported the issue below for the repository {repo_of(iid)}.\n\n<issue>\n{issue}\n</issue>\n\n"


def rating_prompt(iid, x, q):
    return head(iid, x["issue"]) + f"A coding agent produced the patch below.\n\n<patch>\n{x['patch']}\n</patch>\n\n" + q


def comparison_prompt(iid, a, b, q):
    return head(iid, a["issue"]) + (f"Two coding agents produced the patches below.\n\n<patch_A>\n{a['patch']}\n</patch_A>\n\n"
                                    f"<patch_B>\n{b['patch']}\n</patch_B>\n\n") + q


def prior_rows(tag):
    """Reusable temperature-0 rows from the same-conditions run of this model."""
    p = os.path.join(HERE, "derived", f"selfjudge_{tag}.jsonl")
    ratings, comps = {}, {}
    if os.path.exists(p):
        for l in open(p):
            r = json.loads(l)
            if r.get("err") is not None or r.get("parsed") is None:
                continue
            if r["cond"] in ("P0", "P1"):
                ratings[(r["cond"], r["pid"])] = r
            else:
                a, b = (r["pos_pid"], r["neg_pid"]) if r["order"] == "PN" else (r["neg_pid"], r["pos_pid"])
                comps[(r["cond"], a, b)] = r
    return ratings, comps


def run(args):
    P = pools_own(args.own) if args.own else pools(args.cache)
    out = os.path.join(HERE, "derived", f"selection{'-own' if args.own else ''}_{args.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        for l in open(out):
            r = json.loads(l)
            if r.get("err") is None:
                done.add(r["key"])
    old_r, old_c = ({}, {}) if args.own else prior_rows(args.tag)
    jobs, reused = [], []
    for iid, members in P.items():
        for x in members:
            pid = pid_of(iid, x)
            for cond, q, tok in (("P0", Q_P0, TOK_ANSWER), ("P1", Q_P1, TOK_REASON)):
                key = f"{cond}|{pid}"
                meta = dict(key=key, cond=cond, iid=iid, pid=pid, y=x["y"], sample=0, temperature=0)
                if key in done:
                    continue
                if (cond, pid) in old_r:
                    o = old_r[(cond, pid)]
                    reused.append(dict(meta, model=args.model, parsed=o["parsed"], provider=o.get("provider"), cost=0.0, err=None, reused=True))
                else:
                    jobs.append((meta, rating_prompt(iid, x, q), tok, 0))
            for s in range(1, N_SAMPLES + 1):
                key = f"P1s|{pid}|{s}"
                if key not in done:
                    jobs.append((dict(key=key, cond="P1s", iid=iid, pid=pid, y=x["y"], sample=s, temperature=SAMPLE_TEMP),
                                 rating_prompt(iid, x, Q_P1), TOK_REASON, SAMPLE_TEMP))
        for a, b in itertools.permutations(members, 2):
            pa, pb = pid_of(iid, a), pid_of(iid, b)
            for cond, q, tok in (("C0", Q_C0, TOK_ANSWER), ("C1", Q_C1, TOK_REASON)):
                key = f"{cond}|{pa}|{pb}"
                meta = dict(key=key, cond=cond, iid=iid, a_pid=pa, b_pid=pb, a_y=a["y"], b_y=b["y"], temperature=0)
                if key in done:
                    continue
                if (cond, pa, pb) in old_c:
                    o = old_c[(cond, pa, pb)]
                    reused.append(dict(meta, model=args.model, parsed=o["parsed"], provider=o.get("provider"), cost=0.0, err=None, reused=True))
                else:
                    jobs.append((meta, comparison_prompt(iid, a, b, q), tok, 0))
    print(f"{args.model}: pools {len(P)}, reused {len(reused)}, new calls {len(jobs)}", flush=True)
    with open(out, "a") as fh:
        for r in reused:
            fh.write(json.dumps(r) + "\n")
        with concurrent.futures.ThreadPoolExecutor(args.workers) as ex:
            futs = {ex.submit(call, args.model, pr, tok, None, 4, temp): meta for meta, pr, tok, temp in jobs}
            for f in concurrent.futures.as_completed(futs):
                row = dict(futs[f], model=args.model, reused=False)
                row.update(f.result())
                row["parsed"] = parse("P1" if row["cond"] == "P1s" else row["cond"], row["content"])
                fh.write(json.dumps(row) + "\n"); fh.flush()


def choose_by_score(scores):
    """Expected pass rate when picking the top score, ties broken uniformly. scores: list of (score, y)."""
    top = max(s for s, _ in scores)
    tied = [y for s, y in scores if s == top]
    return sum(tied) / len(tied), len(tied)


def analyze(tags, n_boot=2000, seed=0, own=False):
    res = {}
    for tag in tags:
        rows = [json.loads(l) for l in open(os.path.join(HERE, "derived", f"selection{'-own' if own else ''}_{tag}.jsonl")) if l.strip()]
        rows = [r for r in rows if r.get("err") is None]
        by_iid = collections.defaultdict(list)
        for r in rows:
            by_iid[r["iid"]].append(r)
        per_pool, calls = {}, collections.defaultdict(list)
        top_ties = collections.defaultdict(list)
        pair_acc, pair_iid = collections.defaultdict(list), collections.defaultdict(list)
        for iid, R in by_iid.items():
            y = {}
            for r in R:
                if "pid" in r:
                    y[r["pid"]] = r["y"]
            pids = sorted(y)
            if (len(set(y.values())) != 2) if own else (len(pids) != 1 + N_FAIL):
                continue
            p0 = {r["pid"]: r["parsed"] for r in R if r["cond"] == "P0"}
            p1 = {r["pid"]: r["parsed"] for r in R if r["cond"] == "P1"}
            ps = collections.defaultdict(list)
            for r in R:
                if r["cond"] == "P1s" and r["parsed"] is not None:
                    ps[r["pid"]].append(r["parsed"])
            comp = {(r["cond"], r["a_pid"], r["b_pid"]): r["parsed"] for r in R if r["cond"] in ("C0", "C1")}
            acc = {"random": sum(y.values()) / len(pids)}
            # unparsed rating -> lowest possible value (never preferred over a parsed one)
            s0 = [(1 if p0.get(p) == "PASS" else 0, y[p]) for p in pids]
            acc["rating_answer_only"], t0 = choose_by_score(s0)
            s1 = [(p1[p] if p1.get(p) is not None else -1, y[p]) for p in pids]
            acc["rating_reasoning_first"], t1 = choose_by_score(s1)
            sm = [(sum(ps[p]) / len(ps[p]) if ps[p] else -1, y[p]) for p in pids]
            acc["averaged_rating"], tm = choose_by_score(sm)
            top_ties["rating_answer_only"].append(t0); top_ties["rating_reasoning_first"].append(t1); top_ties["averaged_rating"].append(tm)
            for cond, name in (("C0", "comparison_answer_only"), ("C1", "comparison_reasoning_first")):
                wins = collections.Counter()
                for a, b in itertools.permutations(pids, 2):
                    v = comp.get((cond, a, b))
                    if v == "A":
                        wins[a] += 1
                    elif v == "B":
                        wins[b] += 1
                acc[name], _ = choose_by_score([(wins[p], y[p]) for p in pids])
            # rating then comparison among patches tied at the top reasoning-first score
            top = max(s for s, _ in s1)
            tied = [p for p, (s, _) in zip(pids, s1) if s == top]
            if len(tied) == 1:
                acc["rating_then_comparison"] = y[tied[0]]; extra = 0
            else:
                wins = collections.Counter()
                for a, b in itertools.permutations(tied, 2):
                    v = comp.get(("C1", a, b))
                    if v == "A":
                        wins[a] += 1
                    elif v == "B":
                        wins[b] += 1
                acc["rating_then_comparison"], _ = choose_by_score([(wins[p], y[p]) for p in tied])
                extra = len(tied) * (len(tied) - 1)
            n = len(pids)
            for k, c in (("random", 0), ("rating_answer_only", n), ("rating_reasoning_first", n), ("averaged_rating", N_SAMPLES * n),
                         ("comparison_answer_only", n * (n - 1)), ("comparison_reasoning_first", n * (n - 1)),
                         ("rating_then_comparison", n + extra)):
                calls[k].append(c)
            per_pool[iid] = acc
            # same-conditions measures on every pass/fail pair in the pool (ties count as half; comparison = mean of both orders)
            for p, f in ((p, f) for p in pids for f in pids if y[p] == 1 and y[f] == 0):
                for cond, sc in (("P0", {q: int(p0.get(q) == "PASS") for q in pids}), ("P1", {q: s for q, (s, _) in zip(pids, s1)})):
                    pair_acc[cond].append(1.0 if sc[p] > sc[f] else 0.0 if sc[p] < sc[f] else 0.5); pair_iid[cond].append(iid)
                for cond in ("C0", "C1"):
                    v = [comp.get((cond, p, f)) == "A", comp.get((cond, f, p)) == "B"]
                    if comp.get((cond, p, f)) and comp.get((cond, f, p)):
                        pair_acc[cond].append(sum(v) / 2); pair_iid[cond].append(iid)
        iids = sorted(per_pool)
        methods = list(next(iter(per_pool.values())).keys())
        mean = lambda m, ids: sum(per_pool[i][m] for i in ids) / len(ids)
        rng = random.Random(seed); boot = collections.defaultdict(list)
        for _ in range(n_boot):
            s = [rng.choice(iids) for _ in iids]
            for m in methods:
                boot[m].append(mean(m, s) - mean("comparison_reasoning_first", s))
        ci = {m: (round(sorted(v)[int(.025 * n_boot)], 3), round(sorted(v)[int(.975 * n_boot)], 3)) for m, v in boot.items()}
        res[tag] = dict(pools=len(iids),
                        accuracy={m: round(mean(m, iids), 3) for m in methods},
                        minus_comparison_reasoning_first_ci95=ci,
                        calls_per_pool={k: round(sum(v) / len(v), 2) for k, v in calls.items()},
                        mean_patches_tied_at_top={k: round(sum(v) / len(v), 2) for k, v in top_ties.items()},
                        cost_usd=round(sum(r.get("cost") or 0 for r in rows), 4),
                        reused_rows=sum(bool(r.get("reused")) for r in rows), rows=len(rows))
        if own:
            def pa_boot(c, ids):
                v = collections.defaultdict(list)
                for a_, i in zip(pair_acc[c], pair_iid[c]):
                    v[i].append(a_)
                xs = [a_ for i in ids for a_ in v[i]]
                return sum(xs) / len(xs) if xs else float("nan")
            rng = random.Random(seed); bd = []
            for _ in range(n_boot):
                s = [rng.choice(iids) for _ in iids]
                bd.append(pa_boot("C1", s) - pa_boot("P1", s))
            bd.sort()
            res[tag]["pairs"] = dict(n={c: len(pair_acc[c]) for c in ("P0", "P1", "C0", "C1")},
                                     pair_accuracy={c: round(pa_boot(c, iids), 3) for c in ("P0", "P1", "C0", "C1")},
                                     tie_rate={c: round(sum(a_ == 0.5 for a_ in pair_acc[c]) / max(1, len(pair_acc[c])), 3) for c in ("P0", "P1")},
                                     comparison_minus_rating_reasoning_first_ci95=(round(bd[int(.025 * n_boot)], 3), round(bd[int(.975 * n_boot)], 3)))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--cache"); r.add_argument("--own", help="own-attempts data dir instead of --cache"); r.add_argument("--model", required=True); r.add_argument("--tag", required=True)
    r.add_argument("--workers", type=int, default=8)
    z = sp.add_parser("analyze"); z.add_argument("tags", nargs="+"); z.add_argument("--own", action="store_true")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a)
    else:
        print(json.dumps(analyze(a.tags, own=a.own), indent=1))
