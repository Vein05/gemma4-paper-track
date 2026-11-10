#!/usr/bin/env python3
"""How many failing patches of public agents pass every existing test SWE-bench runs (exploratory, 2026-11-09).

No plan was written before this count, and it uses data that had been looked at. It reads SWE-bench's public test
reports for every public mini-SWE-agent entry on the 500 SWE-bench Verified issues.

SWE-bench grades a patch with the issue's tests (FAIL_TO_PASS) and the other existing tests on its list
(PASS_TO_PASS). The list holds tests from the test files that the reference pull request touches. A failing patch is
a wrong fix when every listed other test passes. Many failing "patches" hold no fix (an empty patch, an error
message saved as the patch, only new files, tests or docs), so the main count uses the failing patches that change
an existing source file.

  fetch (needs datasets; about 22,000 small downloads from the public swe-bench-submissions bucket):
      uv run --with datasets python -I failure_census.py fetch
      -> data/public/swe-bench-verified-failure-census/rows.jsonl, one row per entry and issue, and source.json
  analyze (numpy and scipy):
      python3 failure_census.py analyze > derived/failure_census_2026-11-10.json
"""
import collections, concurrent.futures, json, os, re, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(DATA, "public", "swe-bench-verified-failure-census")
ROWS = os.path.join(OUT, "rows.jsonl")
ENTRIES = os.path.join(DATA, "public", "swe-bench-verified-more-writers", "source.json")
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com/bash-only"
MIN_REPORTS = 490   # an entry is used when at least this many of the 500 issues have a report
STRONG = 0.40       # the rank correlation uses entries that solve at least this share of issues
L = lambda p: [json.loads(l) for l in open(p)]

TEST_FILE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$")
DOC_FILE = re.compile(r"\.(rst|md|txt)$|(^|/)docs?/|(^|/)CHANGES|(^|/)AUTHORS")


def patch_class(patch):
    """'code' when the patch changes a line of an existing file that is not a test or doc file; otherwise why not."""
    if not patch or not patch.strip():
        return "empty"
    parts = [x for x in re.split(r"(?m)^(?=diff --git )", patch) if x.startswith("diff --git")]
    if not parts:
        return "not a diff"
    kinds = set()
    for x in parts:
        m = re.match(r"diff --git a/(\S+) b/(\S+)", x)
        f = m.group(2) if m else ""
        head = x.split("\n@@")[0]
        if TEST_FILE.search(f):
            kinds.add("tests")
        elif DOC_FILE.search(f):
            kinds.add("docs")
        elif "new file mode" in head or "\n--- /dev/null" in head:
            kinds.add("new files")
        elif any(l[:1] in "+-" and l[:3] not in ("+++", "---") for l in x.split("\n") if l):
            return "code"
        else:
            kinds.add("file mode")
    return "only " + ", ".join(sorted(kinds))


def get(url):
    """The body, None when the bucket has no such file."""
    for attempt in range(4):
        try:
            return urllib.request.urlopen(url, timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
        except Exception:
            pass
    raise OSError(f"download failed: {url}")


def fetch():
    from datasets import load_dataset
    issues = sorted(load_dataset("princeton-nlp/SWE-bench_Verified", split="test")["instance_id"])
    src = json.load(open(ENTRIES))
    entries = sorted(src["entries"])
    done = {(r["entry"], r["iid"]) for r in L(ROWS)} if os.path.exists(ROWS) else set()

    def one(job):
        entry, iid = job
        body = get(f"{BUCKET}/{entry}/logs/{iid}/report.json")
        row = dict(entry=entry, iid=iid, report=body is not None)
        if body is None:
            return row
        d = json.loads(body)
        d = d[iid] if isinstance(d.get(iid), dict) else d
        ts = d.get("tests_status") or {}
        n = lambda group, key: len((ts.get(group) or {}).get(key, []))
        row.update(applied=bool(d.get("patch_successfully_applied", d.get("patch_exists"))),
                   resolved=bool(d.get("resolved")),
                   issue_pass=n("FAIL_TO_PASS", "success"), issue_fail=n("FAIL_TO_PASS", "failure"),
                   other_pass=n("PASS_TO_PASS", "success"), other_fail=n("PASS_TO_PASS", "failure"))
        if row["applied"] and not row["resolved"]:
            patch = get(f"{BUCKET}/{entry}/logs/{iid}/patch.diff")
            row["patch"] = patch_class(patch.decode("utf-8", "replace") if patch is not None else "")
        return row

    jobs = [(e, i) for e in entries for i in issues if (e, i) not in done]
    os.makedirs(OUT, exist_ok=True)
    with open(ROWS, "a") as out, concurrent.futures.ThreadPoolExecutor(24) as ex:
        for k, row in enumerate(ex.map(one, jobs)):
            out.write(json.dumps(row) + "\n")
            if k % 2000 == 0:
                out.flush()
                print(f"{k} of {len(jobs)}", file=sys.stderr)
    rows = sorted(L(ROWS), key=lambda r: (r["entry"], r["iid"]))
    with open(ROWS, "w") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")
    json.dump(dict(bucket=BUCKET, experiments_commit=src["experiments_commit"], entries=entries, issues=len(issues),
                   files="logs/<issue>/report.json for every entry and issue; logs/<issue>/patch.diff for the failing ones",
                   fields="report: the bucket has a report; applied, resolved: from the report; issue_pass, issue_fail: "
                          "FAIL_TO_PASS tests that pass and fail; other_pass, other_fail: PASS_TO_PASS tests that pass "
                          "and fail; patch: what the failing patch changes (patch_class in scripts/failure_census.py)"),
              open(os.path.join(OUT, "source.json"), "w"), indent=1)
    print(f"{len(rows)} rows, {sum(r['report'] for r in rows)} with a report", file=sys.stderr)


def analyze():
    import numpy as np
    from scipy.stats import spearmanr
    rows = L(ROWS)
    issues = sorted({r["iid"] for r in rows})
    reports = collections.Counter(r["entry"] for r in rows if r["report"])
    fetched = sorted({r["entry"] for r in rows})
    used = [e for e in fetched if reports[e] >= MIN_REPORTS]
    rows = [r for r in rows if r["entry"] in used and r["report"]]
    failing = [r for r in rows if r["applied"] and not r["resolved"]]
    wrong = lambda r: r["other_fail"] == 0
    code = [r for r in failing if r["patch"] == "code"]
    share = lambda rs: dict(wrong_fixes=sum(map(wrong, rs)), failing=len(rs), share=round(sum(map(wrong, rs)) / len(rs), 3))

    E, I = {e: k for k, e in enumerate(used)}, {i: k for k, i in enumerate(issues)}
    S, F, W = (np.zeros((len(used), len(issues))) for _ in range(3))  # solved, failing with code, wrong fix with code
    for r in rows:
        S[E[r["entry"]], I[r["iid"]]] = r["resolved"]
    for r in code:
        F[E[r["entry"]], I[r["iid"]]] = 1
        W[E[r["entry"]], I[r["iid"]]] = wrong(r)

    def corr(ent, iss):
        rate = S[np.ix_(ent, iss)].mean(1)
        sh = W[np.ix_(ent, iss)].sum(1) / F[np.ix_(ent, iss)].sum(1)
        keep = rate >= STRONG
        return float(spearmanr(rate[keep], sh[keep]).statistic)

    all_e, all_i = np.arange(len(used)), np.arange(len(issues))
    rate = S.mean(1)
    strong = np.where(rate >= STRONG)[0]
    rng = np.random.default_rng(0)
    by_issue = [corr(all_e, rng.integers(0, len(issues), len(issues))) for _ in range(2000)]
    by_entry = [corr(rng.choice(strong, len(strong)), all_i) for _ in range(2000)]
    ci = lambda v: [round(float(np.nanpercentile(v, 2.5)), 2), round(float(np.nanpercentile(v, 97.5)), 2)]

    per_entry = {e: dict(solved=round(float(rate[E[e]]), 3), **share([r for r in code if r["entry"] == e]))
                 for e in sorted(used, key=lambda e: rate[E[e]])}
    band = lambda lo, hi: [v for v in per_entry.values() if lo <= v["solved"] < hi]
    pooled = lambda vs: dict(entries=len(vs), wrong_fixes=sum(v["wrong_fixes"] for v in vs),
                             failing=sum(v["failing"] for v in vs),
                             share=round(sum(v["wrong_fixes"] for v in vs) / sum(v["failing"] for v in vs), 3),
                             lowest=min(v["share"] for v in vs), highest=max(v["share"] for v in vs))

    # Issues that an entry of middle strength and a strong entry both fail with a patch that changes code.
    mid = [E[e] for e in used if 0.40 <= rate[E[e]] < 0.60]
    top = [E[e] for e in used if rate[E[e]] >= 0.70]
    both = np.where((F[mid].sum(0) > 0) & (F[top].sum(0) > 0))[0]
    same = lambda ent: round(float(W[np.ix_(ent, both)].sum() / F[np.ix_(ent, both)].sum()), 3)

    # The paper's held-out issues: Gemma's own count beside the public entries that solve 40% to 60% of them.
    held = {r["instance_id"] for run in ("main-a", "main-b") for r in L(os.path.join(DATA, "mcsr-runs", run, "labels.jsonl"))}
    hi = np.array([I[i] for i in sorted(held) if i in I])
    near = [E[e] for e in used if 0.40 <= S[E[e]][hi].mean() <= 0.60]
    held_out = dict(issues=len(hi), entries=len(near), wrong_fixes=int(W[np.ix_(near, hi)].sum()),
                    failing=int(F[np.ix_(near, hi)].sum()),
                    share=round(float(W[np.ix_(near, hi)].sum() / F[np.ix_(near, hi)].sum()), 3))

    no_fix = collections.Counter(r["patch"] for r in failing if r["patch"] != "code")
    print(json.dumps(dict(
        entries_fetched=len(fetched), entries_used=len(used),
        entries_left_out={e: reports[e] for e in fetched if e not in used}, issues=len(issues), reports=len(rows),
        all_failing_patches=share(failing),
        failing_patches_without_a_fix=dict(n=len(failing) - len(code), kinds=dict(no_fix.most_common())),
        failing_patches_that_change_code=share(code),
        with_at_least_5_listed_tests=share([r for r in code if r["other_pass"] + r["other_fail"] >= 5]),
        with_at_least_20_listed_tests=share([r for r in code if r["other_pass"] + r["other_fail"] >= 20]),
        rank_correlation_with_share_solved=dict(entries=int(len(strong)), min_share_solved=STRONG,
                                                value=round(corr(all_e, all_i), 2), ci95_resampling_issues=ci(by_issue),
                                                ci95_resampling_entries=ci(by_entry)),
        entries_solving_40_to_60_percent=pooled(band(0.40, 0.60)),
        entries_solving_60_to_70_percent=pooled(band(0.60, 0.70)),
        entries_solving_70_percent_or_more=pooled(band(0.70, 1.01)),
        same_issues_failed_by_both_groups=dict(issues=int(len(both)), entries_40_to_60_percent=same(mid),
                                               entries_70_percent_or_more=same(top)),
        held_out_issues_entries_solving_40_to_60_percent=held_out,
        per_entry=per_entry), indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "analyze": analyze}[sys.argv[1]]()
