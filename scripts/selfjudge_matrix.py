#!/usr/bin/env python3
"""Matched test of "knows which, not whether": pointwise vs pairwise patch judgment, with and without reasoning.

The 2026-10-04 quick check compared a one-word pointwise verdict (no reasoning) with a pairwise choice that
allowed brief reasoning, and scored pointwise pairs with ties as 0.5. Both favour pairwise. This script crosses
the two factors on the same patches and pairs:

  P0  pointwise, one word PASS/FAIL, no reasoning
  P1  pointwise, brief reasoning, then SCORE: 0-100 (probability the hidden tests pass)
  C0  pairwise, one letter A/B, no reasoning, both orders
  C1  pairwise, brief reasoning, then ANSWER: A/B, both orders

Data: public `nebius/SWE-agent-trajectories` patches (same loader and selection as api_quickcheck.py: issues with
at least one resolved and one unresolved patch, test hunks removed). Model reasoning is switched off at the API
where the model allows it. gpt-oss cannot switch it off: it runs at low reasoning effort with 3,000 extra output
tokens, so its hidden reasoning is present in every condition alike.

Usage:
  python3 selfjudge_matrix.py run --cache DIR --model M --out derived/selfjudge_<tag>.jsonl
  python3 selfjudge_matrix.py run --live ../data/public/swe-bench-live --created-from 2025-02-01 --model M \
      --out derived/selfjudge_live-after_<tag>.jsonl     (before/after cutoff test, spec/post-cutoff-test.md)
  python3 selfjudge_matrix.py analyze derived/selfjudge_*.jsonl
"""
import argparse, collections, concurrent.futures, hashlib, json, os, random, re, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from api_quickcheck import SYSTEM, load, repo_of  # noqa: E402

Q_P0 = ("Question: after this patch is applied, will the maintainers' hidden tests for this issue pass?\n"
        "The hidden tests were written for the upstream fix. They check the behaviour the issue asks for, and tests "
        "that passed before must still pass.\nAnswer with exactly one word: PASS or FAIL.")
Q_P1 = ("Question: after this patch is applied, will the maintainers' hidden tests for this issue pass?\n"
        "The hidden tests were written for the upstream fix. They check the behaviour the issue asks for, and tests "
        "that passed before must still pass.\nExplain briefly, then end your reply with a final line that is exactly "
        "SCORE: <n>, where n is your probability from 0 to 100 that the hidden tests pass.")
Q_C0 = ("Question: exactly one of the two patches above passes the maintainers' hidden tests for this issue. Which one?\n"
        "Do not explain. Your entire reply must be a single letter: A or B.")
Q_C1 = ("Question: exactly one of the two patches above passes the maintainers' hidden tests for this issue. Which one?\n"
        "Explain briefly, then end your reply with a final line that is exactly ANSWER: A or ANSWER: B.")


def call(model, prompt, max_tokens, provider=None, retries=4, temperature=0, reasoning=False):
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": temperature, "max_tokens": max_tokens, "usage": {"include": True}}
    if model.startswith("openai/gpt-oss"):
        # gpt-oss always reasons and cannot switch it off; its hidden reasoning counts against max_tokens, so give
        # it room and ask for low effort. Its "answer only" conditions therefore still include hidden reasoning.
        body["reasoning"] = {"effort": "low"}
        body["max_tokens"] = max_tokens + 3000
    else:
        body["reasoning"] = {"enabled": bool(reasoning)}
    if provider:
        body["provider"] = {"order": provider.split(","), "allow_fallbacks": False}
    err = None
    for k in range(retries):
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=240))
            msg = r["choices"][0]["message"]
            u = r.get("usage") or {}
            return dict(content=(msg.get("content") or "").strip(), provider=r.get("provider"),
                        prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"), cost=u.get("cost"), err=None)
        except Exception as e:
            err = f"{type(e).__name__}: {getattr(e, 'code', '')} {str(e)[:200]}"
            time.sleep(2 * (k + 1))
    return dict(content=None, err=err)


def parse(cond, content):
    if content is None:
        return None
    if cond == "P0":
        m = re.match(r"\W*(PASS|FAIL)\b", content.upper())
        return m.group(1) if m else None
    if cond == "P1":
        m = re.findall(r"SCORE:\s*\**\s*(\d{1,3})", content)
        return min(100, int(m[-1])) if m else None
    if cond == "C0":
        m = re.match(r"\W*([AB])\b", content)
        return m.group(1) if m else None
    m = re.findall(r"ANSWER:\s*\**\s*([AB])\b", content)
    return m[-1] if m else None


def run(a):
    if a.live:
        from live_data import load_live
        sel = load_live(a.live, a.per_label, a.seed, a.created_from, a.created_before, a.max_issues)
    else:
        sel = load(a.cache, a.per_label, a.seed)
    jobs = []
    for iid, (pos, neg) in sel.items():
        head = f"A user reported the issue below for the repository {repo_of(iid)}.\n\n<issue>\n{pos[0]['issue']}\n</issue>\n\n"
        for x in pos + neg:
            pid = f"{iid}|{x['y']}|{hashlib.md5(x['patch'].encode()).hexdigest()[:8]}"
            body = head + f"A coding agent produced the patch below.\n\n<patch>\n{x['patch']}\n</patch>\n\n"
            jobs.append((dict(cond="P0", iid=iid, pid=pid, y=x["y"]), body + Q_P0, 8))
            jobs.append((dict(cond="P1", iid=iid, pid=pid, y=x["y"]), body + Q_P1, a.reason_tokens))
        for j, (p, n) in enumerate(zip(pos, neg)):
            pp = f"{iid}|1|{hashlib.md5(p['patch'].encode()).hexdigest()[:8]}"
            pn = f"{iid}|0|{hashlib.md5(n['patch'].encode()).hexdigest()[:8]}"
            for order in ("PN", "NP"):
                A, B = (p, n) if order == "PN" else (n, p)
                body = head + (f"Two coding agents produced the patches below.\n\n<patch_A>\n{A['patch']}\n</patch_A>\n\n"
                               f"<patch_B>\n{B['patch']}\n</patch_B>\n\n")
                meta = dict(iid=iid, pair=j, pos_pid=pp, neg_pid=pn, order=order, correct="A" if order == "PN" else "B")
                jobs.append((dict(cond="C0", **meta), body + Q_C0, 8))
                jobs.append((dict(cond="C1", **meta), body + Q_C1, a.reason_tokens))
    done = set()
    if os.path.exists(a.out):
        kept = []
        for l in open(a.out):
            r = json.loads(l)
            # --redo-unparsed: drop reasoning-first rows whose answer was cut off or unparseable, so they are asked again
            if a.redo_unparsed and r["cond"] in ("P1", "C1") and r.get("parsed") is None:
                continue
            kept.append(l)
            if r.get("err") is None:
                done.add((r["cond"], r.get("pid") or f"{r['iid']}|{r['pair']}|{r['order']}"))
        if a.redo_unparsed:
            open(a.out, "w").writelines(kept)
    key = lambda m: (m["cond"], m.get("pid") or f"{m['iid']}|{m['pair']}|{m['order']}")
    jobs = [j for j in jobs if key(j[0]) not in done]
    print(f"model {a.model}: issues {len(sel)}, calls to run {len(jobs)}", flush=True)
    with open(a.out, "a") as fh, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(call, a.model, pr, mt, a.provider): meta for meta, pr, mt in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f], model=a.model); row.update(f.result()); row["parsed"] = parse(row["cond"], row["content"])
            fh.write(json.dumps(row) + "\n"); fh.flush()


def analyze(paths, n_boot=2000, seed=0):
    rows = [json.loads(l) for p in paths for l in open(p) if l.strip()]
    out = {}
    for model in sorted({r["model"] for r in rows}):
        R = [r for r in rows if r["model"] == model and r.get("err") is None]
        P = {(r["cond"], r["pid"]): r["parsed"] for r in R if r["cond"] in ("P0", "P1")}
        C = collections.defaultdict(dict)
        pairs = {}
        for r in R:
            if r["cond"] in ("C0", "C1"):
                C[(r["cond"], r["iid"], r["pair"])][r["order"]] = (r["parsed"] == r["correct"]) if r["parsed"] else None
                pairs[(r["iid"], r["pair"])] = (r["pos_pid"], r["neg_pid"])
        per_issue = collections.defaultdict(lambda: collections.defaultdict(list))
        ties = collections.Counter(); unparsed = collections.Counter()
        for (iid, j), (pp, pn) in pairs.items():
            for cond in ("P0", "P1"):
                a_, b_ = P.get((cond, pp)), P.get((cond, pn))
                if a_ is None or b_ is None:
                    unparsed[cond] += 1; continue
                if cond == "P0":
                    a_, b_ = int(a_ == "PASS"), int(b_ == "PASS")
                s = 1.0 if a_ > b_ else 0.0 if a_ < b_ else 0.5
                ties[cond] += int(a_ == b_)
                per_issue[iid][cond].append(s)
                if a_ != b_:
                    per_issue[iid][cond + "_untied"].append(s)
            for cond in ("C0", "C1"):
                o = C.get((cond, iid, j), {})
                if o.get("PN") is None or o.get("NP") is None:
                    unparsed[cond] += 1; continue
                per_issue[iid][cond].append((o["PN"] + o["NP"]) / 2)
                per_issue[iid][cond + "_both"].append(float(o["PN"] and o["NP"]))
                per_issue[iid][cond + "_flip"].append(float(o["PN"] != o["NP"]))
        iids = sorted(per_issue)
        mean = lambda cond, ids: (lambda v: sum(v) / len(v) if v else float("nan"))([s for i in ids for s in per_issue[i][cond]])
        res = {c: mean(c, iids) for c in ("P0", "P1", "C0", "C1", "P0_untied", "P1_untied", "C0_both", "C1_both", "C0_flip", "C1_flip")}
        rng = random.Random(seed); boots = collections.defaultdict(list)
        for _ in range(n_boot):
            s = [rng.choice(iids) for _ in iids]
            for d, (x, y) in dict(gap_noreason=("C0", "P0"), gap_reason=("C1", "P1"), reason_effect_pointwise=("P1", "P0"),
                                  reason_effect_pairwise=("C1", "C0")).items():
                boots[d].append(mean(x, s) - mean(y, s))
        ci = {d: (round(sorted(v)[int(.025 * n_boot)], 3), round(sorted(v)[int(.975 * n_boot)], 3)) for d, v in boots.items()}
        out[model] = dict(issues=len(iids), pairs=len(pairs), acc={k: round(v, 3) for k, v in res.items()},
                          tie_rate={c: round(ties[c] / max(1, len(pairs)), 3) for c in ("P0", "P1")},
                          unparsed=dict(unparsed), ci_95=ci, cost=round(sum(r.get("cost") or 0 for r in R), 4))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--cache"); r.add_argument("--model", required=True); r.add_argument("--out", required=True)
    r.add_argument("--provider", default=None); r.add_argument("--per-label", type=int, default=2)
    r.add_argument("--seed", type=int, default=20261004); r.add_argument("--workers", type=int, default=12)
    r.add_argument("--reason-tokens", type=int, default=900, help="max output tokens for reasoning-first calls")
    r.add_argument("--live", help="SWE-bench-Live submissions dir (live_data.py) instead of --cache")
    r.add_argument("--created-from", default="0000"); r.add_argument("--created-before", default="9999")
    r.add_argument("--max-issues", type=int, default=None, help="random subset of issues (seeded), --live only")
    r.add_argument("--redo-unparsed", action="store_true", help="re-ask reasoning-first calls with no parsed answer")
    z = sp.add_parser("analyze"); z.add_argument("paths", nargs="+")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a)
    else:
        print(json.dumps(analyze(a.paths), indent=1))
