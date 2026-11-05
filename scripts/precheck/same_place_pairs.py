#!/usr/bin/env python3
"""Rebuild the same-place set of 2026-10-28 (spec/bug-token-precheck.md, check 1) without reading any score.

Reuses the loading and similarity code of notes/idea-own-code-surprise-2026-10-28/belief_check.py unchanged (patch
texts from the agent runs and control file, tests stripped; same place = overlap over union of 10-line blocks of the
hunk ranges, at least 0.5). Writes scripts/derived/same_place_pairs_2026-11-02.jsonl: one row per other writer's
failing patch on an issue where the 31B's own patch failed and same place >= 0.5. Run from scripts/."""
import json, os, sys
sys.path.insert(0, os.getcwd())
SRC = os.path.join(os.getcwd(), "..", "notes", "idea-own-code-surprise-2026-10-28", "belief_check.py")
exec(open(SRC).read().split("own_of = ")[0])  # defines pids, y, wr, iss, text, sim (and loads scores, not used here)
own_of = {iss[i]: i for i in range(len(pids)) if wr[i] == W}
rows = []
for i in range(len(pids)):
    if wr[i] == W or y[i] != 0 or iss[i] not in own_of:
        continue
    o = own_of[iss[i]]
    if y[o] != 0:
        continue
    s = sim(text[pids[i]], text[pids[o]])
    if s["same_place"] >= 0.5:
        rows.append(dict(iid=str(iss[i]), own_pid=pids[o], other_pid=pids[i], writer=str(wr[i]), **s,
                         own_patch=text[pids[o]], other_patch=text[pids[i]]))
with open(os.path.join("derived", "same_place_pairs_2026-11-02.jsonl"), "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
print("same-place pairs:", len(rows), "issues:", len({r["iid"] for r in rows}))
