# Filters and the 20-program sample of spec/bigcodebench-full.md.
#   python bcb_full_gate.py <dataset.parquet> <gemma_eval_results.json> <deepseek_eval_results.json> <ref_failed.json>
import json, random, re, sys
import pandas as pd

ds = pd.read_parquet(sys.argv[1]).set_index("task_id")
gem = json.load(open(sys.argv[2]))["eval"]
dsv = json.load(open(sys.argv[3]))["eval"]
ref_failed = set(json.load(open(sys.argv[4])))

fakes = re.compile(r"patch\(|MagicMock|mock_open|Mock\(")
uses_fakes = {t for t in ds.index if fakes.search(ds.loc[t, "test"])}
status = {t: gem[t][0]["status"] for t in ds.index}
ds_status = {t: dsv[t][0]["status"] for t in ds.index}

def rate(ts, st):
    ts = list(ts)
    p = sum(st[t] == "pass" for t in ts)
    return f"{p}/{len(ts)} = {p / len(ts):.1%}"

all_t = list(ds.index)
kept = [t for t in all_t if t not in uses_fakes and t not in ref_failed]
print("Gemma, all tasks:", rate(all_t, status), "| DeepSeek-V3:", rate(all_t, ds_status))
print("Gemma statuses:", pd.Series(status).value_counts().to_dict())
print("tasks with fakes:", len(uses_fakes), "| reference fails:", len(ref_failed),
      "| both:", len(uses_fakes & ref_failed), "| kept:", len(kept))
print("with fakes  Gemma", rate(uses_fakes, status), "DeepSeek", rate(uses_fakes, ds_status))
print("kept        Gemma", rate(kept, status), "DeepSeek", rate(kept, ds_status))
g, d = (lambda t: status[t] == "pass"), (lambda t: ds_status[t] == "pass")
print("kept overlap: both pass", sum(g(t) and d(t) for t in kept), "Gemma only", sum(g(t) and not d(t) for t in kept),
      "DeepSeek only", sum(d(t) and not g(t) for t in kept), "both fail", sum(not g(t) and not d(t) for t in kept))

fail_kept = sorted((t for t in kept if status[t] != "pass"), key=lambda t: int(t.split("/")[1]))
print("Gemma failing programs on kept tasks:", len(fail_kept))
random.seed(0)
sample = random.sample(fail_kept, 20)
print("sample:", [t.split("/")[1] for t in sample])
json.dump({"kept": kept, "uses_fakes": sorted(uses_fakes), "gemma_fail_kept": fail_kept, "sample": sample},
          open("bcb_full_gate.json", "w"), indent=1)
