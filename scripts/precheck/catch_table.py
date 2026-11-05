#!/usr/bin/env python3
"""Check C of spec/bug-token-precheck.md (addendum 2026-11-02): which signals catch the 31B's own failing held-out
patches that the hosted 31B scored 100. Signals: existing-test flag (derived/test_flag_2026-11-02.json), 12B under
100, 26B-A4B under 100, GLM-4.5 at 50 or below, false checkable claim (../data/hand-codes/claims.csv, 31 coded cases).
Run from scripts/: python3 precheck/catch_table.py > derived/catch_table_2026-11-02.json"""
import csv, json, os, sys
sys.path.insert(0, os.getcwd())
SRC = os.path.join(os.getcwd(), "..", "notes", "idea-own-code-surprise-2026-10-28", "belief_check.py")
exec(open(SRC).read().split("own_of = ")[0])
import numpy as np
tf = json.load(open("derived/test_flag_2026-11-02.json"))["per_patch"]
claims = {r["pid"]: r["false_checkable_claim"] == "yes" for r in csv.DictReader(open("../data/hand-codes/claims.csv"))}
rows = []
for i in range(len(pids)):
    if wr[i] != W or y[i] != 0 or X["gemma4-31b"][i] != 100:
        continue
    p = pids[i]
    r = dict(pid=p, tests=bool(tf.get(iss[i], {}).get("flag", 0)), sib12=bool(X["gemma4-12b"][i] < 100),
             sib26=bool(X["gemma4-26b-a4b"][i] < 100), glm=bool(X["glm-4.5"][i] <= 50),
             claim=claims.get(p), coded=p in claims)
    r["any_non_glm"] = r["tests"] or r["sib12"] or r["sib26"] or bool(r["claim"])
    r["none"] = not (r["any_non_glm"] or r["glm"])
    rows.append(r)
n = len(rows)
cnt = lambda k: sum(bool(r[k]) for r in rows)
res = dict(n=n, coded_cases=sum(r["coded"] for r in rows),
           caught={k: cnt(k) for k in ("tests", "sib12", "sib26", "glm", "claim", "any_non_glm", "none")},
           only_tests=sum(r["tests"] and not (r["sib12"] or r["sib26"]) for r in rows),
           claim_unique=sum(bool(r["claim"]) and not (r["tests"] or r["sib12"] or r["sib26"] or r["glm"]) for r in rows),
           tests_or_claim_not_glm=sum((r["tests"] or bool(r["claim"])) and not r["glm"] for r in rows),
           rows=rows)
print(json.dumps(res, indent=1))
