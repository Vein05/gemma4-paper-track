#!/usr/bin/env python3
"""Equally strong writers (spec/matched-writers.md): Gemma 4 31B's extra trust in its own failing held-out patches
against the failing patches of public mini-SWE-agent writers whose resolve rate is within BAND of Gemma's.

  fetch:   patch.diff (public swe-bench-submissions bucket) and labels (SWE-bench/experiments per_instance_details.json)
           of every mini-SWE-agent entry on SWE-bench Verified that the paper does not already use, for the held-out
           issues -> data/public/swe-bench-verified-more-writers/attempts.jsonl and source.json
  select:  resolve rate of every writer on the paper's held-out issues (labels only, no judge score) and the writers
           inside the band -> derived/matched_writers_selection.json, derived/matched_patches.jsonl (failing patches)
  run:     python3 matched_writers.py run --tag gemma4-31b [--redo-unparsed --max-tokens 8000] [--workers 8] [--limit N]
  analyze: python3 matched_writers.py analyze > derived/matched_writers_2026-11-09.json
"""
import argparse, collections, concurrent.futures, json, os, sys, urllib.error, urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from api_quickcheck import strip_tests  # noqa: E402
from fresh_judging import FAMILY, WRITERS, labels, patches, pid_of  # noqa: E402
from live_data import MAX_CHARS  # noqa: E402
from per_writer_leniency import G, GW, J9  # noqa: E402
from selection_test import rating_prompt  # noqa: E402
from selfjudge_matrix import Q_P1, call, parse  # noqa: E402
from stripped_rescore import MODEL  # noqa: E402

RUNS = ["main-a", "main-b"]
OUT = os.path.join(HERE, "..", "data", "public", "swe-bench-verified-more-writers")
ATTEMPTS = os.path.join(OUT, "attempts.jsonl")
SELECTION = os.path.join(HERE, "derived", "matched_writers_selection.json")
PATCHES = os.path.join(HERE, "derived", "matched_patches.jsonl")
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com/bash-only"
RAW = "https://raw.githubusercontent.com/SWE-bench/experiments/{sha}/evaluation/verified/{entry}/per_instance_details.json"
API = "https://api.github.com/repos/SWE-bench/experiments"
BAND = 0.08
# Family of a writer, named as in fresh_judging.FAMILY where a judge of that family exists, so that judge is left out
# of the outside mean on the writer's patches. OpenAI writers take the gpt-oss judges' family.
FAMILY_OF = (("gemini", "google"), ("claude", "anthropic"), ("sonnet", "anthropic"), ("glm", "glm"), ("kimi", "kimi"),
             ("qwen", "qwen"), ("deepseek", "deepseek"), ("minimax", "minimax"), ("devstral", "mistral"),
             ("llama", "llama"), ("gpt", "gpt-oss"), ("o3", "gpt-oss"), ("o4", "gpt-oss"))


def family_of(writer):
    if writer == GW:
        return "gemma"
    return next(f for k, f in FAMILY_OF if k in writer.lower())


def get(url):
    for _ in range(3):
        try:
            return urllib.request.urlopen(url, timeout=60).read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
        except Exception:
            pass
    return None


def fetch(a):
    iids = sorted({json.loads(l)["instance_id"] for r in RUNS
                   for l in open(os.path.join(HERE, "..", "data", "mcsr-runs", r, "preds.jsonl"))})
    sha = json.loads(get(f"{API}/commits/main"))["sha"]
    tree = json.loads(get(f"{API}/git/trees/{sha}?recursive=1"))["tree"]
    entries = sorted({p["path"].split("/")[2] for p in tree
                      if p["path"].startswith("evaluation/verified/") and "_mini-v" in p["path"]})
    entries = [e for e in entries if not any(w in e.lower() for w in WRITERS)]  # the paper's five are already stored
    det = {}
    for e in entries:
        t = get(RAW.format(sha=sha, entry=e))
        if t:
            det[e] = json.loads(t)

    def one(job):
        e, i = job
        return dict(writer=e, instance_id=i, patch=get(f"{BUCKET}/{e}/logs/{i}/patch.diff"),
                    resolved=(det[e].get(i) or {}).get("resolved"))

    os.makedirs(OUT, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(48) as pool, open(ATTEMPTS, "w") as f:
        for r in pool.map(one, [(e, i) for e in sorted(det) for i in iids]):
            f.write(json.dumps(r) + "\n")
    json.dump(dict(experiments_commit=sha, entries=sorted(det), entries_without_details=sorted(set(entries) - set(det)),
                   issues=len(iids), bucket=BUCKET), open(os.path.join(OUT, "source.json"), "w"), indent=1)
    print(len(det), "entries,", len(iids), "issues, experiments commit", sha[:8])


def select(a):
    lab = labels(RUNS)  # the paper's held-out issues and Gemma's labels on them
    P = {pid: x for pid, x in patches(RUNS).items() if x["iid"] in lab}
    for x in P.values():
        if x["writer"] == GW:
            x["y"] = lab[x["iid"]]
        x["source"] = "own" if x["writer"] == GW else "paper"
    issue_text = {x["iid"]: x["issue"] for x in P.values()}
    for l in open(ATTEMPTS):
        r = json.loads(l)
        p = strip_tests(r["patch"] or "")
        if r["instance_id"] in lab and r["resolved"] is not None and p and len(p) <= MAX_CHARS:
            P.setdefault(pid_of(r["instance_id"], r["writer"], p),
                         dict(iid=r["instance_id"], writer=r["writer"], patch=p, y=int(r["resolved"]),
                              issue=issue_text[r["instance_id"]], source="new"))
    by = collections.defaultdict(list)
    for x in P.values():
        by[x["writer"]].append(x["y"])
    table = {w: dict(usable=len(v), passing=int(sum(v)), rate=round(float(np.mean(v)), 4), family=family_of(w))
             for w, v in by.items()}
    half = len(lab) / 2
    for w, t in table.items():  # entries whose labels or patches are unusable
        t["excluded"] = ("no resolved issue (labels unusable)" if t["passing"] == 0
                         else "patches for fewer than half the issues" if t["usable"] < half else None)
    g = table[GW]["rate"]
    band = sorted(w for w, t in table.items() if w != GW and not t["excluded"] and abs(t["rate"] - g) <= BAND)
    for w, t in table.items():
        t["in_band"] = w in band
    rows = [dict(pid=pid, family=family_of(x["writer"]), **x) for pid, x in sorted(P.items())
            if x["y"] == 0 and (x["writer"] == GW or x["writer"] in band)]
    with open(PATCHES, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n = collections.Counter(r["writer"] for r in rows)
    json.dump(dict(issues=len(lab), gemma_rate=g, band=BAND, band_writers=band, failing_patches=dict(n),
                   failing_total=len(rows), writers=dict(sorted(table.items(), key=lambda kv: -kv[1]["rate"]))),
              open(SELECTION, "w"), indent=1)
    print(f"Gemma {g:.3f} on {len(lab)} issues; band writers:", {w: (table[w]['rate'], n[w]) for w in band},
          "; own failing", n[GW], "; total", len(rows))


def run(a):
    rows = [json.loads(l) for l in open(PATCHES)]
    out = os.path.join(HERE, "derived", f"matched_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out):
        done = {r["pid"] for r in map(json.loads, open(out))
                if r.get("err") is None and (r.get("parsed") is not None or not a.redo_unparsed)}
    jobs = [(dict(cond="P1", iid=x["iid"], pid=x["pid"], writer=x["writer"], model=MODEL[a.tag]),
             rating_prompt(x["iid"], x, Q_P1)) for x in rows if x["pid"] not in done][:a.limit]
    print(f"{a.tag}: patches {len(rows)}, new calls {len(jobs)}", flush=True)
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, MODEL[a.tag], pr, a.max_tokens): meta for meta, pr in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); row["parsed"] = parse("P1", row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush()


def scores(prefix, pids):
    """Last parsed score per patch and judge from derived/<prefix>_<judge>.jsonl, and the summed cost."""
    S, cost = collections.defaultdict(dict), 0.0
    for t in J9:
        f = os.path.join(HERE, "derived", f"{prefix}_{t}.jsonl")
        for r in map(json.loads, open(f)) if os.path.exists(f) else []:
            cost += r.get("cost") or 0
            if r.get("err") is None and r.get("parsed") is not None and r["pid"] in pids:
                S[r["pid"]][t] = r["parsed"]
    return S, cost


def analyze(a):
    meta = {r["pid"]: r for r in map(json.loads, open(PATCHES))}
    S, cost = scores("matched", meta)
    pids = sorted(p for p in meta if len(S[p]) == len(J9))
    wr = np.array([meta[p]["writer"] for p in pids]); fam = np.array([meta[p]["family"] for p in pids])
    iss = np.array([meta[p]["iid"] for p in pids])
    X = {t: np.array([S[p][t] for p in pids], float) for t in J9}

    def extra(X, i):  # Gemma minus the outside judges on patch i; judges of the writer's family left out
        return X[G][i] - np.mean([X[m][i] for m in J9 if m != G and FAMILY[m] != fam[i]])
    D = np.array([extra(X, i) for i in range(len(pids))])
    T = (X[G] == 100).astype(float) * 100  # Gemma gives the top score
    writers = sorted(set(wr) - {GW}); families = sorted({family_of(w) for w in writers})

    def stats(idx):
        m = lambda v, sel: float(v[idx][sel].mean()) if sel.any() else np.nan
        w_idx = wr[idx]
        r = {}
        for name, v in (("extra_trust", D), ("share_100", T)):
            own = m(v, w_idx == GW)
            wm = {w: m(v, w_idx == w) for w in writers}
            fm = {f: float(np.nanmean([wm[w] for w in writers if family_of(w) == f])) for f in families}
            r[f"{name}_own_minus_matched_family_balanced"] = own - float(np.nanmean(list(fm.values())))
            r[f"{name}_own_minus_matched_pooled"] = own - m(v, w_idx != GW)
            for f in families:
                rest = [fm[k] for k in families if k != f]
                r[f"{name}_own_minus_matched_without_{f}"] = own - float(np.nanmean(rest))
        return r

    issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
    rng = np.random.default_rng(0); B = collections.defaultdict(list)
    for _ in range(2000):
        idx = np.concatenate([by[i] for i in rng.choice(issues, len(issues))])
        for k, v in stats(idx).items():
            B[k].append(v)
    full = stats(np.arange(len(pids)))
    res = {k: dict(value=round(v, 1), ci95=[round(float(np.nanpercentile(B[k], 2.5)), 1),
                                            round(float(np.nanpercentile(B[k], 97.5)), 1)]) for k, v in full.items()}
    sel = json.load(open(SELECTION))
    panel = np.array([X[G][i] - D[i] for i in range(len(pids))])
    res["per_writer"] = {w: dict(family=family_of(w), resolve_rate=sel["writers"][w]["rate"], failing=int((wr == w).sum()),
                                 extra_trust=round(float(D[wr == w].mean()), 1), gemma_mean=round(float(X[G][wr == w].mean()), 1),
                                 outside_mean=round(float(panel[wr == w].mean()), 1),
                                 gemma_share_100=round(float(T[wr == w].mean()), 1)) for w in [GW] + writers}
    # drift: the October scores of the patches that the paper already used (own, and band writers among its five)
    S0, _ = scores("fresh", meta)
    old = [i for i, p in enumerate(pids) if len(S0[p]) == len(J9)]
    X0 = {t: np.array([S0[pids[i]][t] for i in old], float) for t in J9}
    X1 = {t: X[t][old] for t in J9}
    D0 = np.array([X0[G][k] - np.mean([X0[m][k] for m in J9 if m != G and FAMILY[m] != fam[i]]) for k, i in enumerate(old)])
    wo = wr[old]
    res["drift_october_to_now"] = dict(
        patches=len(old),
        mean_abs_diff={t: round(float(np.abs(X1[t] - X0[t]).mean()), 1) for t in J9},
        mean_shift={t: round(float((X1[t] - X0[t]).mean()), 1) for t in J9},
        extra_trust_own=dict(october=round(float(D0[wo == GW].mean()), 1), now=round(float(D[old][wo == GW].mean()), 1)),
        extra_trust_paper_band_writers=dict(october=round(float(D0[wo != GW].mean()), 1),
                                            now=round(float(D[old][wo != GW].mean()), 1)))
    p = res["extra_trust_own_minus_matched_family_balanced"]
    res["reading"] = ("no detectable preference against equally strong writers" if p["ci95"][0] <= 0 <= p["ci95"][1]
                      else "shrinks but remains" if p["value"] < 9.9
                      else "writer strength does not explain the gap among equally strong writers")
    res.update(judges=J9, band=sel["band"], gemma_rate=sel["gemma_rate"], band_writers=writers, families=families,
               patches_in_set=len(meta), patches_scored_by_all=len(pids), issues=len(issues),
               cost_usd=round(cost, 2))
    print(json.dumps({G: res}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("fetch"); sp.add_parser("select"); sp.add_parser("analyze")
    r = sp.add_parser("run"); r.add_argument("--tag", required=True, choices=sorted(MODEL))
    r.add_argument("--workers", type=int, default=8); r.add_argument("--redo-unparsed", action="store_true")
    r.add_argument("--max-tokens", type=int, default=3000); r.add_argument("--limit", type=int)
    a = ap.parse_args()
    {"fetch": fetch, "select": select, "run": run, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
