#!/usr/bin/env python3
"""Do gpt-oss-120b and Llama-4-Maverick favor their own LiveCodeBench programs under our measure (spec/lcb-same-model.md)?

Inputs and outputs in data/lab-runs/lcb-same-model/: messages.jsonl (from scripts/lab/lcb_same_model_lab.py dump),
<writer>.jsonl (programs), <writer>_codegeneration_output_eval_all.json (grades), <writer>_p1.jsonl (judging prompts, from
scripts/lab/lcb_sweep_prompts.py), scores_<judge>.jsonl.

  python3 lcb_same_model.py write --writer gpt-oss-120b [--limit 5]
  python3 lcb_same_model.py judge --writer gpt-oss-120b
  python3 lcb_same_model.py analyze > derived/lcb_same_model_2026-11-05.json
"""
import argparse, collections, concurrent.futures, glob, json, os, sys, time, urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import selfjudge_matrix  # noqa: E402
from fresh_judging import FAMILY  # noqa: E402

ROOT = os.path.join(HERE, "..")
D = os.path.join(ROOT, "data", "lab-runs", "lcb-same-model")
PROGRAMS = os.path.join(ROOT, "data", "livecodebench-pilot", "judging", "programs.jsonl")
MODEL = {"gpt-oss-120b": "openai/gpt-oss-120b", "llama-4-maverick": "meta-llama/llama-4-maverick",
         "gemma4-31b": "google/gemma-4-31b-it", "gpt-oss-20b": "openai/gpt-oss-20b", "qwen35-9b": "qwen/qwen3.5-9b",
         "glm47-flash": "z-ai/glm-4.7-flash"}
J6 = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "gpt-oss-120b", "llama-4-maverick"]
OWN = {"gpt-oss-120b": "gpt-oss-120b", "llama-4-maverick": "llama-4-maverick", "gemma4-31b": "gemma-4-31b"}
WRITER_FAMILY = {"gemma-4-31b": FAMILY["gemma4-31b"], "claude-3.5-sonnet": None, "deepseek-v3": None,
                 "gpt-oss-120b": FAMILY["gpt-oss-120b"], "llama-4-maverick": FAMILY["llama-4-maverick"]}
CAP = 3.00  # spec: hard stop on recorded spending


def spent():
    total = 0.0
    for f in glob.glob(os.path.join(D, "*.jsonl")):
        if os.path.basename(f) != "messages.jsonl" and not f.endswith("_p1.jsonl"):
            total += sum(r.get("cost") or 0 for r in map(json.loads, open(f)))
    return total


def chat(model, messages, max_tokens):
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens, "usage": {"include": True}}
    if model.startswith("openai/gpt-oss"):
        body["reasoning"] = {"effort": "low"}
        body["max_tokens"] = max_tokens + 3000
    else:
        body["reasoning"] = {"enabled": False}
    err = None
    for k in range(4):
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json",
                                      "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=600))
            c, u = r["choices"][0], r.get("usage") or {}
            return dict(output=(c["message"].get("content") or ""), finish_reason=c.get("finish_reason"),
                        provider=r.get("provider"), prompt_tokens=u.get("prompt_tokens"),
                        completion_tokens=u.get("completion_tokens"), cost=u.get("cost"), err=None)
        except Exception as e:
            err = f"{type(e).__name__}: {getattr(e, 'code', '')} {str(e)[:200]}"
            time.sleep(2 * (k + 1))
    return dict(output=None, err=err)


def pool(jobs, fn, out, workers):
    """Run fn(job) -> row; append rows to out; stop when the spec's spending cap is reached."""
    total = spent()
    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(fn, j) for j in jobs]
        for f in concurrent.futures.as_completed(futs):
            row = f.result()
            fh.write(json.dumps(row) + "\n"); fh.flush()
            total += row.get("cost") or 0
            if total > CAP:
                print(f"cap ${CAP} reached (${total:.3f}); stopping", flush=True)
                for g in futs:
                    g.cancel()
                break
    print(f"{os.path.basename(out)}: spent so far ${total:.3f}", flush=True)


def write(a):
    out = os.path.join(D, f"{a.writer}.jsonl")
    done = {r["question_id"] for r in map(json.loads, open(out)) if r.get("err") is None} if os.path.exists(out) else set()
    probs = [p for p in map(json.loads, open(os.path.join(D, "messages.jsonl"))) if p["question_id"] not in done][:a.limit]
    print(f"{a.writer}: {len(done)} done, {len(probs)} to write", flush=True)

    def one(p):
        return dict(question_id=p["question_id"], difficulty=p["difficulty"], platform=p["platform"],
                    contest_date=p["contest_date"], writer=a.writer, max_tokens=8000,
                    **chat(MODEL[a.writer], p["messages"], 8000))
    pool(probs, one, out, a.workers)


def judges_of(writer):
    """The model itself and its outside judges (spec, step 4)."""
    return [writer] + [k for k in J6 if k != writer and FAMILY[k] != WRITER_FAMILY[writer]]


def judge(a):
    prompts = list(map(json.loads, open(os.path.join(D, f"{a.writer}_p1.jsonl"))))
    for tag in judges_of(a.writer):
        out = os.path.join(D, f"scores_{tag}.jsonl")
        rows = list(map(json.loads, open(out))) if os.path.exists(out) else []
        ok = {r["pid"] for r in rows if r.get("err") is None and r.get("parsed") is not None}
        tried = {r["pid"] for r in rows}
        for limit, todo in ((3000, [p for p in prompts if p["pid"] not in tried]), (8000, None)):
            if todo is None:  # unparsed answers asked again at 8,000 tokens
                rows = list(map(json.loads, open(out))) if os.path.exists(out) else []
                ok = {r["pid"] for r in rows if r.get("err") is None and r.get("parsed") is not None}
                todo = [p for p in prompts if p["pid"] not in ok]
            print(f"{tag} on {a.writer}: {len(todo)} calls at {limit} tokens", flush=True)

            def one(p, limit=limit, tag=tag):
                r = chat(MODEL[tag], [{"role": "system", "content": p["system"]}, {"role": "user", "content": p["prompt"]}], limit)
                content = (r.pop("output") or "").strip()
                return dict(pid=p["pid"], iid=p["iid"], writer=p["writer"], cond="P1", model=MODEL[tag], content=content,
                            parsed=selfjudge_matrix.parse("P1", content), max_tokens=limit, **r)
            pool(todo, one, out, a.workers)


def scores(path):
    out = {}
    for r in map(json.loads, open(path)):
        if r.get("err") is None and r.get("parsed") is not None:
            out[r["pid"]] = r["parsed"]
    return out


def analyze(_):
    old = {r["pid"]: dict(iid=r["iid"], writer=r["writer"], y=r["y"]) for r in map(json.loads, open(PROGRAMS))}
    S_old = {t: scores(os.path.join(HERE, "derived", f"lcb_{t}.jsonl")) for t in J6}
    common = {p for p in old if all(p in S_old[t] for t in J6)}  # as third_party_lite.analyze
    res = {}

    def one(j, drop=()):
        w = OWN[j]
        outside = [k for k in J6 if k != j and FAMILY[k] != WRITER_FAMILY[w] and k not in drop]
        S = {t: dict(S_old[t]) for t in J6}
        items = {p: x for p, x in old.items() if p in common}
        info = {}
        if j != "gemma4-31b":
            grade = {e["question_id"]: int(bool(e["graded_list"][0]))
                     for e in json.load(open(os.path.join(D, f"{w}_codegeneration_output_eval_all.json")))}
            ids = {r["question_id"] for r in map(json.loads, open(os.path.join(D, "messages.jsonl")))}
            new = {r["pid"]: dict(iid=r["iid"], writer=w, y=grade[r["iid"]]) for r in map(json.loads, open(os.path.join(D, f"{w}_p1.jsonl")))}
            for t in judges_of(w):
                S[t].update(scores(os.path.join(D, f"scores_{t}.jsonl")))
            need = [t for t in judges_of(w) if t not in drop]
            scored = {p: x for p, x in new.items() if all(p in S[t] for t in need)}
            items.update(scored)
            info = dict(pass_rate_292=round(sum(grade[q] for q in ids) / len(ids), 3), programs_with_code=len(new),
                        programs_scored_by_all=len(scored), programs_lost=len(ids) - len(scored))
        pids = sorted(items)
        y = np.array([items[p]["y"] for p in pids]); wr = np.array([items[p]["writer"] for p in pids])
        iss = np.array([items[p]["iid"] for p in pids])
        Xj = np.array([S[j][p] for p in pids], float)
        panel = np.array([np.mean([S[k][p] for k in outside if FAMILY[k] != WRITER_FAMILY[wr[i]]]) for i, p in enumerate(pids)])
        d = Xj - panel

        def value(idx):
            f = idx[y[idx] == 0]
            return d[f[wr[f] == w]].mean() - d[f[wr[f] != w]].mean()
        issues = sorted(set(iss)); by = {i: np.where(iss == i)[0] for i in issues}
        rng = np.random.default_rng(0); boot = []
        for _b in range(2000):
            boot.append(value(np.concatenate([by[i] for i in rng.choice(issues, len(issues))])))
        allidx = np.arange(len(pids)); f = y == 0
        own, rest = f & (wr == w), f & (wr != w)
        lo, hi = float(np.nanpercentile(boot, 2.5)), float(np.nanpercentile(boot, 97.5))
        raw_own, raw_rest = float(Xj[own].mean()), float(Xj[rest].mean())
        if own.sum() < 30:
            reading = "too few to test"
        elif lo > 0:
            reading = "lenient" if raw_own > raw_rest else "reference artefact"
        else:
            reading = "not lenient"
        return dict(leniency_difference=round(float(value(allidx)), 3), ci95=[round(lo, 3), round(hi, 3)], reading=reading,
                    outside_judges=outside, own_failing=int(own.sum()), other_failing=int(rest.sum()),
                    raw_own_failing=round(raw_own, 1), raw_other_failing=round(raw_rest, 1),
                    panel_own_failing=round(float(panel[own].mean()), 1), panel_other_failing=round(float(panel[rest].mean()), 1),
                    scored100_own_failing=round(float((Xj[own] == 100).mean()), 3),
                    scored100_other_failing=round(float((Xj[rest] == 100).mean()), 3), **info)

    res["gemma4-31b (code check)"] = one("gemma4-31b")
    for m in ("gpt-oss-120b", "llama-4-maverick"):
        if os.path.exists(os.path.join(D, f"{m}_codegeneration_output_eval_all.json")):
            res[m] = one(m)
            # exploratory, added after reading the result: most lost programs lack a Qwen3.5-9B score
            s = one(m, drop=("qwen35-9b",))
            res[m]["exploratory_without_qwen35"] = {k: s[k] for k in ("leniency_difference", "ci95", "own_failing", "other_failing", "programs_lost")}
    rs = [res[m]["reading"] for m in ("gpt-oss-120b", "llama-4-maverick") if m in res]
    res["reading_for_paper"] = ("both lenient" if rs == ["lenient"] * 2 else "neither lenient" if rs == ["not lenient"] * 2
                                else "report each model" if len(rs) == 2 else "incomplete")
    res["spent_usd"] = round(spent(), 3)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    w = sp.add_parser("write"); w.add_argument("--writer", required=True); w.add_argument("--limit", type=int); w.add_argument("--workers", type=int, default=12)
    j = sp.add_parser("judge"); j.add_argument("--writer", required=True); j.add_argument("--workers", type=int, default=12)
    sp.add_parser("analyze")
    a = ap.parse_args()
    os.makedirs(D, exist_ok=True)
    {"write": write, "judge": judge, "analyze": analyze}[a.cmd](a)
