# Which failing programs fail only tests about raised errors or empty/invalid input (exploratory, after the gate sample)
import json, re, sys
import pandas as pd
D = "<repo>/data/bigcodebench-full"
ds = pd.read_parquet("bcb-full-ds/v0.1.4.parquet").set_index("task_id")
ev = json.load(open(f"{D}/gemma4-31b-full-complete_eval_results.json"))["eval"]
g = json.load(open("bcb_full_gate.json"))
def edge(task, name, msg):
    m = re.search(rf"(    def {re.escape(name)}\(.*?)(?=\n    def |\Z)", ds.loc[task, "test"], re.S)
    src = m.group(1) if m else ""
    return ("assertRaises" in src or "not raised" in str(msg)
            or re.search(r"empty|invalid|error|none|non_numeric|nonexist|missing", name, re.I) is not None)
def edge_only(t):
    det = ev[t][0]["details"]
    return isinstance(det, dict) and len(det) > 0 and all(edge(t, n, m) for n, m in det.items())
bugs = {"913", "620", "395", "1103", "1082"}
for t in g["sample"]:
    n = t.split("/")[1]
    print(n, "bug" if n in bugs else "-", "edge-only" if edge_only(t) else "")
left = [t for t in g["gemma_fail_kept"] if not edge_only(t)]
print("failing programs on kept tasks:", len(g["gemma_fail_kept"]), "| not edge-only:", len(left))
