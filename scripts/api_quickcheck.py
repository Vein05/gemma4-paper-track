#!/usr/bin/env python3
"""Quick check of the verdict probe on PUBLIC data only (no competition data).

Data: Hugging Face `nebius/SWE-agent-trajectories` rows (agent patches with a resolved label,
`target`), cached as datasets-server JSON pages in --cache. Judge: google/gemma-4-31b-it on
OpenRouter, pinned to Novita (bf16), thinking off, temperature 0.

Two measures, both on issues that have at least one resolved and one unresolved patch:
  verdict : issue + patch -> PASS/FAIL, asked twice (repeatability)
  afc     : issue + patch A + patch B, exactly one passes -> "A" or "B", both orders
The patches were written by SWE-agent models, not by Gemma, so this tests whether Gemma can
judge patches with task difficulty held fixed. It is not the self-knowledge test.

Usage: python3 api_quickcheck.py --cache DIR --out results.jsonl [--per-label 2] [--workers 8]
"""
import argparse, collections, hashlib, concurrent.futures, glob, json, os, random, re, time, urllib.error, urllib.request

MODEL = "google/gemma-4-31b-it"
PROVIDER = {"order": ["Novita"], "allow_fallbacks": False, "require_parameters": True, "quantizations": ["bf16"]}
CFG = dict(model=MODEL, provider=PROVIDER, reasoning_off=True, logprobs=True, base_url=None)  # overridden by CLI flags
SYSTEM = ("You are an expert Python maintainer. You review a proposed fix for a reported issue. "
          "You cannot run code; judge from the material given.")
PROTECTED = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$")
Q_VERDICT = ("Question: after this patch is applied, will the maintainers' hidden tests for this issue pass?\n"
             "The hidden tests were written for the upstream fix. They check the behaviour the issue asks for, and tests "
             "that passed before must still pass.\nAnswer with exactly one word: PASS or FAIL.")
Q_AFC = ("Question: exactly one of the two patches above passes the maintainers' hidden tests for this issue. Which one?\n"
         "Explain briefly, then end your reply with a final line that is exactly ANSWER: A or ANSWER: B.")


def strip_tests(patch):
    parts = re.split(r"(?m)^(?=diff --git )", patch or "")
    keep = [p for p in parts if p.strip() and not ((m := re.match(r"diff --git a/(\S+) b/", p)) and PROTECTED.search(m.group(1)))]
    return "".join(keep).strip()


def issue_text(traj):
    u = next((m for m in traj if m.get("role") == "user"), {})
    txt = u.get("text") or ""
    m = re.search(r"ISSUE:\n(.*?)\n\nINSTRUCTIONS:", txt, re.S)
    return (m.group(1) if m else "").strip()


def repo_of(iid):
    return iid.rsplit("-", 1)[0].replace("__", "/")


def load(cache, per_label, seed):
    rows = []
    for f in sorted(glob.glob(os.path.join(cache, "rows_*.json"))):
        try:
            rows += [r["row"] for r in json.load(open(f)).get("rows", [])]
        except Exception:
            pass
    by = collections.defaultdict(list)
    for r in rows:
        p = strip_tests(r.get("generated_patch"))
        if p:
            by[r["instance_id"]].append(dict(iid=r["instance_id"], model=r["model_name"], y=int(str(r["target"]) == "True"),
                                              patch=p, issue=issue_text(r["trajectory"])))
    rng = random.Random(seed)
    sel = {}
    for iid, v in sorted(by.items()):
        if not v[0]["issue"]:
            continue
        uniq = {}
        for x in v:
            uniq.setdefault((x["y"], x["patch"]), x)  # drop duplicate patches
        pos = [x for (y, _), x in uniq.items() if y == 1]
        neg = [x for (y, _), x in uniq.items() if y == 0]
        if pos and neg:
            rng.shuffle(pos); rng.shuffle(neg)
            sel[iid] = (pos[:per_label], neg[:per_label])
    return sel


def call(prompt, max_tokens=2, retries=4):
    body = {"model": CFG["model"], "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": max_tokens}
    if CFG["logprobs"]:
        body.update(logprobs=True, top_logprobs=20)
    if CFG["base_url"]:  # local vLLM server: thinking off through the chat template, no routing fields
        body["chat_template_kwargs"] = {"enable_thinking": False}
    else:
        if CFG["reasoning_off"]:
            body["reasoning"] = {"enabled": False}
        if CFG["provider"]:
            body["provider"] = CFG["provider"]
    url = (CFG["base_url"] or "https://openrouter.ai/api/v1") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if not CFG["base_url"]:
        headers["Authorization"] = "Bearer " + os.environ["OPENROUTER_API_KEY"]
    for k in range(retries):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            ch = r["choices"][0]
            lp = ((ch.get("logprobs") or {}).get("content") or [{}])[0]
            content = (ch["message"].get("content") or "").strip()
            m = re.findall(r"ANSWER:\s*\**\s*([AB])\b", content)
            return dict(text=(m[-1] if m else content[:20]), tok_logprob=lp.get("logprob"), n_chars=len(content), judge=CFG["model"],
                        provider=r.get("provider"), prompt_tokens=(r.get("usage") or {}).get("prompt_tokens"),
                        cost=(r.get("usage") or {}).get("cost"), err=None)
        except Exception as e:  # retry on HTTP or parse errors
            err = f"{type(e).__name__}: {getattr(e, 'code', '')} {str(e)[:200]}"
            time.sleep(2 * (k + 1))
    return dict(text=None, err=err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-label", type=int, default=2)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--only", choices=["verdict", "afc"], default=None)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--provider", default=None, help="comma-separated provider order; default Novita bf16 for Gemma, router default otherwise")
    ap.add_argument("--no-logprobs", action="store_true")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL of a self-hosted server, e.g. http://127.0.0.1:18000/v1")
    ap.add_argument("--keep-reasoning", action="store_true", help="do not send reasoning.enabled=false (models without a reasoning switch)")
    a = ap.parse_args()
    CFG.update(model=a.model, logprobs=not a.no_logprobs, reasoning_off=not a.keep_reasoning, base_url=a.base_url,
               provider=(PROVIDER if a.model == MODEL and a.provider is None else
                         ({"order": a.provider.split(","), "allow_fallbacks": False} if a.provider else None)))
    sel = load(a.cache, a.per_label, a.seed)
    jobs = []
    for iid, (pos, neg) in sel.items():
        head = f"A user reported the issue below for the repository {repo_of(iid)}.\n\n<issue>\n{pos[0]['issue']}\n</issue>\n\n"
        for x in pos + neg:
            pid = f"{iid}|{x['y']}|{hashlib.md5(x['patch'].encode()).hexdigest()[:8]}"
            pr = head + f"A coding agent produced the patch below.\n\n<patch>\n{x['patch']}\n</patch>\n\n{Q_VERDICT}"
            for rep in (1, 2):
                jobs.append((dict(kind="verdict", iid=iid, pid=pid, y=x["y"], author=x["model"], rep=rep), pr))
        for j, (p, n) in enumerate(zip(pos, neg)):
            for order in ("PN", "NP"):
                A, B = (p, n) if order == "PN" else (n, p)
                pr = head + (f"Two coding agents produced the patches below.\n\n<patch_A>\n{A['patch']}\n</patch_A>\n\n"
                             f"<patch_B>\n{B['patch']}\n</patch_B>\n\n{Q_AFC}")
                jobs.append((dict(kind="afc", iid=iid, pair=j, order=order, correct="A" if order == "PN" else "B"), pr))
    if a.only:
        jobs = [(m, pr) for m, pr in jobs if m["kind"] == a.only]
    print(f"issues {len(sel)}  jobs {len(jobs)}", flush=True)
    done = 0
    with open(a.out, "w") as fh, concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(call, pr, 2 if meta["kind"] == "verdict" else 800): meta for meta, pr in jobs}
        for f in concurrent.futures.as_completed(futs):
            row = dict(futs[f]); row.update(f.result()); fh.write(json.dumps(row) + "\n"); done += 1
            if done % 50 == 0:
                print("done", done, flush=True)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
