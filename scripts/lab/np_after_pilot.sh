#!/bin/bash
# Waits for the pilot, sets aside warning-affected issues, lists the thinking-on test issues, then runs np_tests.sh
# (spec/nonpython-rubber-stamp.md, addendum).
cd <workdir>/gemma4-paper-track/ml || exit 1
until grep -q ALL_DONE logs/np_pilot.log; do sleep 30; done
echo "pilot done $(date -u +%FT%TZ)"
sleep 30
<workdir>/swe-env/venv20/bin/python - <<'P'
import glob, json, os, shutil
d = json.load(open("data/public/swe-bench-multilingual/issues.json"))["language"] if os.path.exists("data/public/swe-bench-multilingual/issues.json") else None
ids = [l.strip() for l in open("np_pilot_ids.txt") if l.strip()]
preds = json.load(open("runs/nonpython/preds.json"))
os.makedirs("runs/nonpython-before-fix", exist_ok=True)
shutil.copy("runs/nonpython/preds.json", "runs/nonpython-before-fix/preds.json")
rerun, think = [], []
for i in ids:
    f = f"runs/nonpython/{i}/{i}.traj.json"
    t = json.load(open(f)) if os.path.exists(f) else None
    warned = t and any("Skipping mount" in str(m.get("content")) for m in t["messages"] if m["role"] == "tool")
    if warned or t is None:
        rerun.append(i)
        preds.pop(i, None)
        if t:
            shutil.move(f"runs/nonpython/{i}", f"runs/nonpython-before-fix/{i}")
    elif not (preds.get(i) or {}).get("model_patch") and not i.startswith(("caddyserver", "gin-gonic", "gohugoio", "hashicorp", "prometheus")):
        think.append(i)
json.dump(preds, open("runs/nonpython/preds.json", "w"), indent=1)
open("np_rerun_ids.txt", "w").write("\n".join(rerun) + ("\n" if rerun else ""))
open("np_think_ids.txt", "w").write("\n".join(think) + ("\n" if think else ""))
print("rerun", rerun); print("think", think)
P
bash np_tests.sh
