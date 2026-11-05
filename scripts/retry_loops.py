"""Repeated failing tool calls in existing public agent runs (spec/retry-loops.md).

No model calls. Reads public traces downloaded to a local folder and writes counts only.

Usage:
  python3 retry_loops.py analyze --hf <dir with n-pelleriti datasets> --rishav <rishav repo clone> \
      > derived/retry_loops_summary_<date>.json
  python3 retry_loops.py sample --hf ... --rishav ... --group G2 --n 20   # hand check (prints loops)

Groups (spec): G1 Gemma/competition harness (rishav), G2 Gemma/SWE-agent, G3 Qwen3.5-27B/SWE-agent,
G4 Gemma/opencode (two runs), zeroclaw, openclaw, G5 Qwen3.5-27B/openclaw.
"""
import argparse, glob, json, os, random, re, sys
from collections import Counter, defaultdict

# ---------- normalization ----------
WS = re.compile(r"\s+")
NOISE = [
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<UUID>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    (re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|seconds)\b"), "<DUR>"),
    (re.compile(r"/tmp/[\w./-]+"), "<TMP>"),
    (re.compile(r'"(elapsed_s|duration_ms|timestamp|time)"\s*:\s*[\d.]+'), r'"\1": <N>'),
]


def norm(s):
    if not isinstance(s, str):
        s = json.dumps(s, sort_keys=True, default=str)
    for rx, rep in NOISE:
        s = rx.sub(rep, s)
    return WS.sub(" ", s).strip()


def canon_args(a):
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            return WS.sub(" ", a).strip()
    return WS.sub(" ", json.dumps(a, sort_keys=True, default=str)).strip()


# ---------- error classes (spec: ERROR_PATTERNS; first match wins) ----------
ERROR_PATTERNS = [
    ("parser_merge", re.compile(r"mandatory input parameters are not present", re.I)),
    ("policy_block", re.compile(r"(blocked|not allowed) by security policy", re.I)),
    ("edit_target", re.compile(r"did not appear verbatim|No replacement was performed|old_?string[^\n]{0,80}not found"
                               r"|could not find (the )?(string|text)|found multiple|multiple (occurrences|matches)"
                               r"|oldString|must be unique", re.I)),
    ("missing_param", re.compile(r"missing (required )?(parameter|argument)|parameter `?\w+`? is required|"
                                 r"required (parameter|argument)|Invalid (arguments?|parameters?)", re.I)),
    ("file_not_found", re.compile(r"No such file or directory|does not exist|FileNotFoundError|ENOENT|"
                                  r"path not found|file not found", re.I)),
    ("cmd_not_found", re.compile(r"command not found|not recognized as", re.I)),
    ("timeout", re.compile(r"timed? ?out|timeout", re.I)),
    ("traceback", re.compile(r"Traceback \(most recent call last\)|SyntaxError|IndentationError|ModuleNotFoundError|"
                             r"ImportError|NameError|AttributeError|TypeError|ValueError", re.I)),
    ("nonzero_exit", re.compile(r'"exit_code"\s*:\s*[1-9]|exit (code|status) [1-9]|returned non-zero', re.I)),
]


def error_class(text, flagged):
    for name, rx in ERROR_PATTERNS:
        if rx.search(text or ""):
            return name
    return "flagged_other" if flagged else None


PAGINATION = re.compile(r"^(scroll_down|scroll_up)\b")


# ---------- loaders: each returns list of runs ----------
# run = dict(group, model, harness, task, resolved (True/False/None), calls=[dict(tool, key, res, err)])

def mkcall(tool, args, result, flagged=False):
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return dict(tool=tool, key=tool + "|" + canon_args(args), res=norm(text), err=error_class(text[:20000], flagged))


def load_rishav(root):
    runs = []
    for d in sorted(glob.glob(os.path.join(root, "logs/remote/base/train/*/"))):
        t = os.path.basename(d.rstrip("/"))
        tf, rf = os.path.join(d, "traces", f"trace_{t}.json"), os.path.join(d, "results", f"{t}.json")
        if not (os.path.exists(tf) and os.path.exists(rf)):
            continue
        tr, res = json.load(open(tf)), json.load(open(rf))
        calls = []
        for s in tr["steps"]:
            tcs = s.get("tool_calls") or []
            obs = (s.get("observation") or {}).get("content", "")
            for tc in tcs:
                flagged = False
                try:
                    flagged = json.loads(obs).get("status") not in (None, "ok")
                except Exception:
                    pass
                calls.append(mkcall(tc["function_name"], tc.get("arguments"), obs, flagged))
        runs.append(dict(group="G1", model="gemma4-31b", harness="competition", task=t,
                         resolved=bool(res.get("resolved")), calls=calls))
    return runs


def sweagent_labels(hf, ds):
    rep = [f for f in glob.glob(os.path.join(hf, ds, "official_reports", "*.json")) if "smoke" not in f][0]
    r = json.load(open(rep))
    lab = {i: True for i in r.get("resolved_ids", [])}
    lab.update({i: False for i in r.get("unresolved_ids", []) + r.get("empty_patch_ids", [])})
    lab.update({i: None for i in r.get("error_ids", [])})
    return lab


def load_sweagent(hf, ds, group, model):
    lab = sweagent_labels(hf, ds)
    runs = []
    for f in sorted(glob.glob(os.path.join(hf, ds, "sweagent_results", "*", "*", "*.traj"))):
        if "smoke" in f:
            continue
        task = os.path.basename(f)[:-5]
        tr = json.load(open(f))["trajectory"]
        calls = []
        for s in tr:
            a = (s.get("action") or "").strip()
            if not a or PAGINATION.match(a):
                continue
            tool = a.split()[0]
            calls.append(mkcall(tool, a, s.get("observation") or ""))
        runs.append(dict(group=group, model=model, harness="sweagent", task=task, resolved=lab.get(task, False),
                         calls=calls))
    return runs


def results_labels(f):
    lab = {}
    for l in open(f):
        r = json.loads(l)
        task = r["task_id"].removeprefix("swe_")
        ok = r.get("score_status") == "valid_scored"
        lab[task] = bool(r.get("correct")) if ok else (False if not (r.get("predicted") or "").strip() else None)
    return lab


def load_openclaw(f, group, model):
    runs = []
    for l in open(f):
        r = json.loads(l)
        task = r["task_id"].removeprefix("swe_")
        ok = r.get("score_status") == "valid_scored"
        resolved = bool(r.get("correct")) if ok else (False if not (r.get("predicted") or "").strip() else None)
        tr, calls = r.get("trajectory") or [], []
        for i, s in enumerate(tr):
            if s.get("type") != "tool_use":
                continue
            nxt = tr[i + 1] if i + 1 < len(tr) and tr[i + 1].get("role") == "tool" else {}
            for tc in s.get("tool_calls") or []:
                flagged = bool(nxt.get("is_error") or nxt.get("error"))
                calls.append(mkcall(tc.get("tool", "?"), tc.get("input"), nxt.get("content", ""), flagged))
        runs.append(dict(group=group, model=model, harness="openclaw", task=task, resolved=resolved, calls=calls))
    return runs


def load_opencode(hf, ds):
    lab = results_labels(glob.glob(os.path.join(hf, ds, "results", "*.jsonl"))[0])
    runs = []
    for f in sorted(glob.glob(os.path.join(hf, ds, "results", "*", "artifacts", "*", "workspace", "opencode_output.jsonl"))):
        task = f.split("/artifacts/")[1].split("/")[0].removeprefix("swe_")
        calls = []
        for l in open(f):
            try:
                e = json.loads(l)
            except Exception:
                continue
            if e.get("type") != "tool_use":
                continue
            p = e["part"]; st = p.get("state", {})
            out = st.get("output") if st.get("status") != "error" else st.get("error")
            calls.append(mkcall(p.get("tool", "?"), st.get("input"), out or "", st.get("status") == "error"))
        runs.append(dict(group="G4", model="gemma4-31b", harness="opencode-" + ds[-6:], task=task,
                         resolved=lab.get(task), calls=calls))
    return runs


def load_zeroclaw(hf, ds):
    lab = results_labels(glob.glob(os.path.join(hf, ds, "results", "*.jsonl"))[0])
    runs = []
    for f in sorted(glob.glob(os.path.join(hf, ds, "results", "*", "artifacts", "*", "workspace", "runtime_trace.jsonl"))):
        task = f.split("/artifacts/")[1].split("/")[0].removeprefix("swe_")
        calls, pending = [], None
        for l in open(f):
            e = json.loads(l)
            if e.get("event_type") == "tool_call_start":
                pending = e["payload"]
            elif e.get("event_type") == "tool_call_result" and pending is not None:
                out = e["payload"].get("output", "")
                calls.append(mkcall(pending.get("tool", "?"), pending.get("arguments"), out, not e.get("success", True)))
                pending = None
        runs.append(dict(group="G4", model="gemma4-31b", harness="zeroclaw", task=task, resolved=lab.get(task),
                         calls=calls))
    return runs


def load_all(hf, rishav):
    runs = load_rishav(rishav)
    runs += load_sweagent(hf, "alphadiana-sweagent-gemma4-directllm-20260727", "G2", "gemma4-31b")
    runs += load_sweagent(hf, "alphadiana-sweagent-qwen35-directllm-20260728", "G3", "qwen3.5-27b")
    runs += load_opencode(hf, "alphadiana-swe-mini-opencode-gemma4-20260725-v04")
    runs += load_opencode(hf, "alphadiana-swe-mini-opencode-gemma4-20260602-818023")
    runs += load_zeroclaw(hf, "alphadiana-swe-mini-zeroclaw-gemma4-20260724-r6m2")
    runs += load_openclaw(glob.glob(os.path.join(hf, "alphadiana-swe-mini-openclaw-gemma4-20260724-k9q7", "results", "*.jsonl"))[0],
                          "G4", "gemma4-31b")
    runs += load_openclaw(glob.glob(os.path.join(hf, "alphadiana-swe-mini-qwen35-27b-20260729", "full_run", "*.jsonl"))[0],
                          "G5", "qwen3.5-27b")
    return runs


# ---------- measures ----------
def loops(calls):
    """Maximal blocks of >=3 consecutive calls with the same key and the same result."""
    out, i = [], 0
    while i < len(calls):
        j = i
        while j + 1 < len(calls) and calls[j + 1]["key"] == calls[i]["key"] and calls[j + 1]["res"] == calls[i]["res"]:
            j += 1
        if j - i + 1 >= 3:
            out.append((i, j))
        i = j + 1
    return out


def run_stats(r):
    c = r["calls"]
    L = loops(c)
    futile = sum(1 for k in range(1, len(c)) if c[k]["key"] == c[k - 1]["key"] and c[k]["res"] == c[k - 1]["res"])
    causes = [c[i]["err"] or "no_error" for i, _ in L]
    nxt_err = [(c[k]["key"] == c[k - 1]["key"]) for k in range(1, len(c)) if c[k - 1]["err"]]
    nxt_ok = [(c[k]["key"] == c[k - 1]["key"]) for k in range(1, len(c)) if not c[k - 1]["err"]]
    return dict(n_calls=len(c), futile=futile, loop=bool(L),
                loop_nonparser=any(x != "parser_merge" for x in causes),
                loop_calls=sum(j - i + 1 for i, j in L), ends_in_loop=bool(L) and L[-1][1] == len(c) - 1,
                causes=causes, loop_tools=[c[i]["tool"] for i, _ in L], nxt_err=nxt_err, nxt_ok=nxt_ok)


def boot(runs, f, B=2000, seed=20261005):
    """Point estimate and 95% interval of f(list of runs), resampling tasks (clusters)."""
    by = defaultdict(list)
    for r in runs:
        by[r["task"]].append(r)
    keys, rng, vals = list(by), random.Random(seed), []
    for _ in range(B):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in by[k]]
        v = f(s)
        if v is not None:
            vals.append(v)
    vals.sort()
    est = f(runs)
    lo, hi = (vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]) if vals else (None, None)
    return dict(est=None if est is None else round(est, 4), ci=[None if lo is None else round(lo, 4),
                                                                None if hi is None else round(hi, 4)])


def share(pred, cond=lambda r: True):
    def f(rs):
        s = [r for r in rs if cond(r)]
        return sum(pred(r) for r in s) / len(s) if s else None
    return f


def summarize(runs):
    for r in runs:
        r["st"] = run_stats(r)
    unres = lambda r: r["resolved"] is False
    res = lambda r: r["resolved"] is True
    out = {}
    groups = defaultdict(list)
    for r in runs:
        groups[(r["group"], r["harness"])].append(r)
        groups[(r["group"], "all")].append(r)
    groups[("gemma_pooled", "G1+G2+G4")] = [r for r in runs if r["group"] in ("G1", "G2", "G4")]
    for (g, h), rs in sorted(groups.items()):
        if h == "all" and len({r["harness"] for r in rs}) == 1:
            continue
        pooled_err = [x for r in rs for x in r["st"]["nxt_err"]]
        pooled_ok = [x for r in rs for x in r["st"]["nxt_ok"]]
        cause_runs, cause_loops, tools = Counter(), Counter(), Counter()
        for r in rs:
            cause_loops.update(r["st"]["causes"]); cause_runs.update(set(r["st"]["causes"])); tools.update(r["st"]["loop_tools"])
        loop_runs = [r for r in rs if r["st"]["loop"]]
        out[f"{g}/{h}"] = dict(
            runs=len(rs), resolved=sum(res(r) for r in rs), unresolved=sum(unres(r) for r in rs),
            label_unknown=sum(r["resolved"] is None for r in rs),
            calls_median=sorted(r["st"]["n_calls"] for r in rs)[len(rs) // 2],
            m1_unresolved_with_nonparser_loop=boot(rs, share(lambda r: r["st"]["loop_nonparser"], unres)),
            m2_any_loop_all=boot(rs, share(lambda r: r["st"]["loop"])),
            m2_any_loop_unresolved=boot(rs, share(lambda r: r["st"]["loop"], unres)),
            m2_any_loop_resolved=boot(rs, share(lambda r: r["st"]["loop"], res)),
            m3_futile_share_mean=boot(rs, lambda s: sum(r["st"]["futile"] / max(r["st"]["n_calls"], 1) for r in s) / len(s)),
            m3_futile_share_pooled=round(sum(r["st"]["futile"] for r in rs) / max(1, sum(r["st"]["n_calls"] for r in rs)), 4),
            m3_loop_calls_share_pooled=round(sum(r["st"]["loop_calls"] for r in rs) / max(1, sum(r["st"]["n_calls"] for r in rs)), 4),
            m4_p_identical_after_error=round(sum(pooled_err) / len(pooled_err), 4) if pooled_err else None,
            m4_n_error_results=len(pooled_err),
            m4_p_identical_after_other=round(sum(pooled_ok) / len(pooled_ok), 4) if pooled_ok else None,
            m5_loop_runs_ending_in_loop=f"{sum(r['st']['ends_in_loop'] for r in loop_runs)}/{len(loop_runs)}",
            m6_loop_causes_by_loop=dict(cause_loops.most_common()), m6_loop_causes_by_run=dict(cause_runs.most_common()),
            loop_tools=dict(tools.most_common(8)),
            share_loop_runs_parser_only=round(sum(1 for r in loop_runs if not r["st"]["loop_nonparser"]) / len(loop_runs), 4) if loop_runs else None,
        )
    # m7: same harness, same tasks; paired by task
    for a, b, h in [("G2", "G3", "sweagent"), ("G4", "G5", "openclaw")]:
        A = {r["task"]: r for r in runs if r["group"] == a and r["harness"] == h}
        B = {r["task"]: r for r in runs if r["group"] == b and r["harness"] == h}
        common = sorted(set(A) & set(B))
        pairs = [dict(task=t, a=A[t], b=B[t]) for t in common]
        def diff(key):
            return lambda s: sum(key(p["a"]) - key(p["b"]) for p in s) / len(s)
        out[f"m7_{a}_minus_{b}_{h}"] = dict(
            tasks=len(common),
            any_loop=boot(pairs, diff(lambda r: r["st"]["loop"])),
            futile_share=boot(pairs, diff(lambda r: r["st"]["futile"] / max(r["st"]["n_calls"], 1))),
            nonparser_loop_unresolved_both=boot([p for p in pairs if p["a"]["resolved"] is False and p["b"]["resolved"] is False],
                                                diff(lambda r: r["st"]["loop_nonparser"])),
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["analyze", "sample"])
    ap.add_argument("--hf", required=True)
    ap.add_argument("--rishav", required=True)
    ap.add_argument("--group", default="G2")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    runs = load_all(a.hf, a.rishav)
    if a.cmd == "analyze":
        json.dump(summarize(runs), sys.stdout, indent=1)
        return
    rng = random.Random(1)
    L = [(r, i, j) for r in runs if r["group"] == a.group for i, j in loops(r["calls"])]
    for r, i, j in rng.sample(L, min(a.n, len(L))):
        c = r["calls"][i]
        print(f"## {r['harness']} {r['task']} resolved={r['resolved']} calls {i}-{j} of {len(r['calls'])} cause={c['err']}")
        print("   CALL", c["key"][:300]); print("   RES ", c["res"][:300])


if __name__ == "__main__":
    main()
