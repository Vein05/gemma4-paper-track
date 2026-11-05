import json, re, sys
import pandas as pd
D = "<repo>/data/bigcodebench-full"
ds = pd.read_parquet(sys.argv[1]).set_index("task_id")
ev = json.load(open(f"{D}/gemma4-31b-full-complete_eval_results.json"))["eval"]
for n in sys.argv[2:]:
    k = f"BigCodeBench/{n}"
    r, e = ds.loc[k], ev[k][0]
    print("=" * 30, k, e["status"])
    print("--- PROMPT\n" + r["complete_prompt"].strip())
    sol = e["solution"]
    sol = sol[sol.find(r["code_prompt"].strip()[:40], 1):] if sol.count(r["code_prompt"].strip()[:40]) > 1 else sol
    print("--- GEMMA\n" + sol.strip()[:3500])
    det = e["details"]
    print("--- DETAILS")
    for name, msg in (det.items() if isinstance(det, dict) else [("all", det)]):
        print(f"[{name}]", str(msg)[-600:])
    print("--- FAILING TESTS")
    for name in (list(det)[:3] if isinstance(det, dict) else []):
        m = re.search(rf"(    def {re.escape(name)}\(.*?)(?=\n    def |\Z)", r["test"], re.S)
        if m:
            print(m.group(1)[:1000])
    print("--- setUp" )
    m = re.search(r"(    def setUp\(.*?)(?=\n    def |\Z)", r["test"], re.S)
    if m: print(m.group(1)[:600])
