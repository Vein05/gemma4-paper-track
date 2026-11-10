#!/usr/bin/env python3
"""Issues whose reference fix breaks an existing test (exploratory, 2026-11-09; no plan was written first).

The existing-test check (existing_test_gate.py) also ran on each issue's reference fix, with the repository's tests
as they were before the fix. When the reference fix breaks one of them, the test may assert the behaviour that the
issue changes. We call such a test outdated when the reference pull request edits or deletes it.

  build (needs datasets; downloads each test file at the issue's base commit from GitHub):
      uv run --with datasets python -I outdated_test_issues.py build
      -> data/outdated-test-issues/reference_fix_breaks.jsonl, one row per issue whose reference fix was held back
  analyze (standard library only):
      python3 outdated_test_issues.py analyze > derived/outdated_test_issues_2026-11-10.json

The check runs at most four test files near the changed code, so the counts are lower bounds.
"""
import ast, collections, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(DATA, "outdated-test-issues", "reference_fix_breaks.jsonl")
SETS = (("held-out", os.path.join(DATA, "lab-runs", "existing-test-gate"), "princeton-nlp/SWE-bench_Verified"),
        ("lite", os.path.join(DATA, "lab-runs", "lite-repair", "gate"), "princeton-nlp/SWE-bench_Lite"))
L = lambda p: [json.loads(l) for l in open(p)]
# Read by hand (2026-11-09): the reference fix was held back for a reason other than an outdated test.
OTHER = {"psf__requests-1963": "network errors in a test that the pull request leaves unchanged",
         "matplotlib__matplotlib-23987": "a warning about the version string of the patched tree, in a test file "
                                         "that the pull request does not touch",
         "sympy__sympy-13031": "a recursion error in a test file that the pull request does not touch"}


def reference_runs(gate):
    """The check's result on the reference fix of each issue: issue -> run, for the issues it could check."""
    last = {}
    for r in L(os.path.join(gate, "runs.jsonl")):
        if r["kind"] == "patch" and r["writer"] == "gold":
            last[r["pid"]] = r
    return {r["instance_id"]: r for r in last.values() if r.get("status") == "checked"}


def changed_lines(test_patch, path, source):
    """For one file of a diff: whether the diff touches it, deletes it, and which old lines it removes or inserts at.
    A hunk is placed by its text when its header line numbers do not match the base file."""
    removed, inserted, touched, deleted = set(), set(), False, False
    base = source.split("\n")
    for part in re.split(r"(?m)^(?=diff --git )", test_patch):
        m = re.match(r"diff --git a/(\S+) b/(\S+)", part)
        if not m or m.group(1) != path:
            continue
        touched = True
        deleted = "deleted file mode" in part.split("\n@@")[0]
        for hunk in re.split(r"(?m)^(?=@@ )", part)[1:]:
            lines = hunk.split("\n")
            start = int(re.match(r"@@ -(\d+)", lines[0]).group(1))
            body = [l for l in lines[1:] if not l.startswith("\\")]
            old_block = [l[1:] for l in body if l[:1] in (" ", "-")]
            while body and body[-1] == "":
                body.pop()
            if old_block and base[start - 1:start - 1 + len(old_block)] != old_block:
                found = [k + 1 for k in range(len(base) - len(old_block) + 1) if base[k:k + len(old_block)] == old_block]
                if found:
                    start = min(found, key=lambda c: abs(c - start))
            old = start
            for l in body:
                if l.startswith("-"):
                    removed.add(old); old += 1
                elif l.startswith("+"):
                    inserted.add(old)
                else:
                    old += 1
    return touched, deleted, removed, inserted


def test_lines(source, name):
    """First and last line of the test function that a SWE-bench test id names, or None."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    cls = fn = doc = None
    m = re.match(r"(\w+) \(([\w.]+)\)", name)
    if m:
        fn, cls = m.group(1), m.group(2).split(".")[-1]
    elif "::" in name or name.startswith("test"):
        parts = [re.sub(r"\[.*$", "", p) for p in name.split("::") if not p.endswith(".py")]
        fn, cls = parts[-1], parts[-2] if len(parts) > 1 else None
    m2 = re.match(r"(\w+) \(([\w.]+)\.(\w+)\)$", name)
    if m2 and m2.group(3) == m2.group(1):
        fn, cls = m2.group(1), m2.group(2).split(".")[-1]
    else:
        doc = name.strip()
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and (cls is None or node.name == cls):
            for f in node.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        f.name == fn or (doc and (ast.get_docstring(f) or "").strip().split("\n")[0] == doc)):
                    return f.lineno - len(f.decorator_list), f.end_lineno
        if cls is None and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            best = (node.lineno - len(node.decorator_list), node.end_lineno)
    return best


def build():
    from datasets import load_dataset
    rows = []
    for name, gate, dataset in SETS:
        issues = {r["instance_id"]: r for r in load_dataset(dataset, split="test")}
        for iid, run in sorted(reference_runs(gate).items()):
            if run.get("decision") != "block":
                continue
            inst, tests = issues[iid], []
            for key, status in sorted(run["broken"].items()):
                path, test = key.split("::", 1)
                url = f"https://raw.githubusercontent.com/{inst['repo']}/{inst['base_commit']}/{path}"
                source = urllib.request.urlopen(url, timeout=60).read().decode("utf-8", "replace")
                touched, deleted, removed, inserted = changed_lines(inst["test_patch"], path, source)
                span = test_lines(source, test)
                if span is None:
                    how = "test not found in the file"
                elif deleted:
                    how = "deletes the file"
                elif any(span[0] <= x <= span[1] for x in removed):
                    how = "deletes the test" if all(x in removed for x in range(span[0], span[1] + 1)) else "edits the test"
                elif any(span[0] < x <= span[1] for x in inserted):
                    how = "edits the test"
                else:
                    how = "edits the file but not the test" if touched else "does not touch the file"
                tests.append(dict(file=path, test=test, result=status, reference_pull_request=how))
            edited = sum(t["reference_pull_request"] in ("edits the test", "deletes the test") for t in tests)
            row = dict(set=name, instance_id=iid, outdated_test=bool(edited) and iid not in OTHER,
                       broken_tests_edited_or_deleted=edited, broken_tests=tests)
            if iid in OTHER:
                row["other_reason"] = OTHER[iid]
            rows.append(row)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")
    print(f"{len(rows)} issues, {sum(r['outdated_test'] for r in rows)} with an outdated test", file=sys.stderr)


def analyze():
    rows = L(OUT)
    res, total = {}, collections.Counter()
    for name, gate, _ in SETS:
        runs = reference_runs(gate)
        held_back = {i for i, r in runs.items() if r.get("decision") == "block"}
        mine = {r["instance_id"]: r for r in rows if r["set"] == name}
        assert set(mine) == held_back, f"{name}: the list and the check's runs disagree"
        outdated = sorted(i for i, r in mine.items() if r["outdated_test"])
        res[name] = dict(issues_checked=len(runs), reference_fix_held_back=len(held_back),
                         with_an_outdated_test=len(outdated), share=round(len(outdated) / len(runs), 3),
                         held_back_for_another_reason={i: r["other_reason"] for i, r in sorted(mine.items())
                                                       if not r["outdated_test"]})
        total.update(checked=len(runs), outdated=len(outdated))
    kinds = collections.Counter(t["reference_pull_request"] for r in rows if r["outdated_test"] for t in r["broken_tests"])
    res["both"] = dict(issues_checked=total["checked"], with_an_outdated_test=total["outdated"],
                       share=round(total["outdated"] / total["checked"], 3))
    res["broken_tests_of_those_issues"] = dict(kinds.most_common())

    # The outdated tests of an issue: the reference fix breaks them and the pull request edits or deletes them.
    tests = {(r["set"], r["instance_id"]): {t["file"] + "::" + t["test"] for t in r["broken_tests"]
                                             if t["reference_pull_request"] in ("edits the test", "deletes the test")}
             for r in rows if r["outdated_test"]}
    # Held-out patches of the six writers on those issues, by what they do to the outdated tests their check ran.
    gate = SETS[0][1]
    meta = {m["pid"]: m for m in L(os.path.join(gate, "meta.jsonl"))}
    last = {r["pid"]: r for r in L(os.path.join(gate, "runs.jsonl")) if r["kind"] == "patch"}
    c = collections.Counter()
    for r in last.values():
        key = ("held-out", r["instance_id"])
        if r["writer"] == "gold" or r.get("status") != "checked" or r["pid"] not in meta or key not in tests:
            continue
        ran = [t for t in tests[key] if t.split("::")[0] in r["selected"]]
        if ran:
            kind = "breaks_every_outdated_test" if all(t in r["broken"] for t in ran) else "keeps_one_passing"
            c[kind, "correct" if meta[r["pid"]]["y"] else "failing"] += 1
    res["held_out_patches_on_those_issues"] = {
        k: dict(correct=c[k, "correct"], failing=c[k, "failing"]) for k in ("breaks_every_outdated_test", "keeps_one_passing")}
    # Gemma's correct Lite patches that the check held back (the set lite_repair.py analyzes).
    lite = os.path.dirname(SETS[1][1])
    lab = lambda p: {r["instance_id"]: r.get("resolved") for r in L(p)}
    start, ref = lab(os.path.join(lite, "start", "labels.jsonl")), lab(os.path.join(lite, "reference", "labels.jsonl"))
    lmeta = {m["pid"]: m for m in L(os.path.join(SETS[1][1], "meta.jsonl"))}
    ldec = {r["pid"]: r for r in L(os.path.join(SETS[1][1], "runs.jsonl")) if r["kind"] == "patch"}
    good = [m["iid"] for m in lmeta.values() if m["writer"] == "gemma-4-31b"
            and ldec.get(m["pid"], {}).get("decision") == "block" and ref.get(m["iid"]) is True and start.get(m["iid"]) is True]
    mine = [i for i in good if ("lite", i) in tests]
    res["lite_correct_patches_held_back"] = dict(n=len(good), on_an_issue_with_an_outdated_test=len(mine),
                                                 other=sorted(set(good) - set(mine)))
    # What the repair did to them. As in lite_repair.py: an empty submission fails, other ungraded runs keep the grade.
    empty = lambda p: p.get("exit_status") == "Submitted" and p.get("patch_empty", not (p.get("model_patch") or "").strip())
    for arm, name in (("tests", "broken_with_the_tests_shown"), ("review", "broken_with_a_second_look")):
        after = lab(os.path.join(lite, arm, "labels.jsonl"))
        preds = {r["instance_id"]: r for r in L(os.path.join(lite, arm, "preds.jsonl"))}
        passes = lambda i: bool(after[i]) if after.get(i) is not None else not empty(preds.get(i, {}))
        res["lite_correct_patches_held_back"][name] = sum(not passes(i) for i in mine)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"build": build, "analyze": analyze}[sys.argv[1]]()
