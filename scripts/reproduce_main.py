#!/usr/bin/env python3
"""Recompute the main paper's claims from the released data. Run through ../reproduce.sh, which sets up the environment.

Works in .reproduce/work, a copy of scripts/ and data/, so the repository's own files stay as they are. Downloads only
the files listed in reproduce_manifest.tsv plus Gemma's SWE-bench Lite patches, which the repository leaves out because
that run declares no license. Each analysis runs with a file-open trace, and the run fails if a downloaded file was
not read. No model is called and no GPU is used: judge answers, agent runs and test results are the released ones.
"""
import collections, concurrent.futures as cf, csv, hashlib, json, os, re, runpy, shutil, subprocess, sys, time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(ROOT, ".reproduce")
WORK, CACHE, OUT = (os.path.join(BASE, d) for d in ("work", "cache", "out"))

HF_REPO = "vein05/gemma4-paper-track-data"
HF_REV = "a9359db253fc160e7b1e3875f167b56f985ac75e"
LITE_REPO = "dougalldeepmind/2026-10-10-swebench-gemma4-lite-gemma-v2"
LITE_REV = "1c5f3d3be50e4ca6ceb17654987fd34e6cf23f96"

J9 = "gemma4-31b,gpt-oss-20b,qwen35-9b,glm47-flash,qwen3-coder,gpt-oss-120b,glm-4.5,kimi-k2,llama-4-maverick"
J7 = "gemma4-31b,gpt-oss-20b,qwen35-9b,glm47-flash,qwen3-coder,gpt-oss-120b,llama-4-maverick"
J6 = "gemma4-31b,gpt-oss-20b,qwen35-9b,glm47-flash,gpt-oss-120b,llama-4-maverick"
ACTOR = "../data/lab-runs/judge-as-actor"
# Output name (same as the summary committed in scripts/derived/), then the command run from scripts/.
STEPS = [
    ("fresh_replication_2026-10-06.json", f"fresh_judging.py analyze --judges {J9} --runs main-a,main-b"),
    ("third_party_lite_2026-11-01.json", f"third_party_lite.py analyze --judges {J7}"),
    ("lcb_judging_2026-11-01.json", f"lcb_judging.py analyze --judges {J6}"),
    ("other_models_heldout_2026-10-22.json", "other_models_heldout.py"),
    ("lcb_sweep_2026-11-04.json", "lcb_sweep_analysis.py"),
    ("lcb_same_model_2026-11-05.json", "lcb_same_model.py analyze"),
    ("belief_vs_recognition_2026-11-03.json", "belief_vs_recognition.py"),
    ("gemma_sizes_2026-10-28.json", "gemma_sizes_analysis.py --sizes gemma4-12b,gemma4-26b-a4b"),
    ("lcb_blind_spot_2026-11-03.json", "lcb_blind_spot.py"),
    ("rubber_stamp_reasons_2026-10-22.json", "rubber_stamp_reasons.py agree"),
    ("strong_writer_leniency_2026-11-04.txt", "strong_writer_leniency.py"),
    ("thinking_mode_2026-10-22.json", "thinking_mode.py"),
    ("judge_as_actor_2026-11-04.json",
     f"judge_actor.py analyze --jobs {ACTOR}/jobs.jsonl --runs gemma={ACTOR}/gemma gptoss={ACTOR}/gptoss"),
    ("sft_pilot_run2_2026-11-05.json", "sft_pilot.py analyze --scores ../data/lab-runs/sft-pilot/run2/scores.jsonl"),
    ("existing_test_gate_2026-11-05.json", "existing_test_gate.py analyze"),
    ("test_repair_2026-11-05.json", "test_repair.py analyze"),
    ("repair_trace_audit_2026-11-05.json", "repair_trace_audit_2026_11_05.py"),
    ("repair_seeds_2026-11-06.json", "repair_seeds.py"),
    ("tie_break_2026-10-22.json", "tie_break.py"),
    ("stripped_files_rescore_2026-11-03.json", "stripped_rescore.py analyze"),
    ("gemma_31b_local_2026-10-28.json", "gemma_sizes_analysis.py --sizes gemma4-31b-local"),
    ("paper_counts_2026-11-05.json", "paper_counts.py"),
]


def fetch(url, dest):
    tmp = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "gemma4-paper-track-reproduce"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            os.replace(tmp, dest)
            return
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pull_manifest():
    """Download the manifest's files (cached, checked by sha256) into the work copy. Returns their data/ paths."""
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(HERE, "reproduce_manifest.tsv")) if l.strip()]

    def one(row):
        path, digest = row[0], row[1]
        cached = os.path.join(CACHE, "hf", path)
        if not (os.path.exists(cached) and sha256(cached) == digest):
            fetch(f"https://huggingface.co/datasets/{HF_REPO}/resolve/{HF_REV}/{path}", cached)
            if sha256(cached) != digest:
                sys.exit(f"checksum mismatch: {path}")
        dest = os.path.join(WORK, "data", path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(cached, dest)
        return "data/" + path

    with cf.ThreadPoolExecutor(8) as ex:
        done = list(ex.map(one, rows))
    mb = sum(int(r[2]) for r in rows) / 1e6
    print(f"Downloaded from Hugging Face: {len(done)} files, {mb:.1f} MB")
    return done


def restore_lite_patches():
    """Put back the text of Gemma's Lite patches that the belief test compares, from the other team's public run.
    Only patches all seven judges scored. Each is checked against the hash in its pid."""
    sys.path.insert(0, os.path.join(WORK, "scripts"))
    from third_party_lite import GEMMA, pid_of, strip_tests
    path = os.path.join(WORK, "data", "public", "third-party-lite", "patches.jsonl")
    rows = [json.loads(l) for l in open(path)]
    seen = collections.Counter()
    for tag in J7.split(","):
        pids = set()
        for r in map(json.loads, open(os.path.join(WORK, "scripts", "derived", f"lite_{tag}.jsonl"))):
            if r.get("err") is None and r.get("parsed") is not None:
                pids.add(r["pid"])
        seen.update(pids)
    need = [r for r in rows if r["writer"] == GEMMA and seen[r["pid"]] == len(J7.split(","))]

    def one(r):
        rel = r["source"].removeprefix("gemma/")
        cached = os.path.join(CACHE, "lite", rel)
        if not os.path.exists(cached):
            fetch(f"https://huggingface.co/datasets/{LITE_REPO}/resolve/{LITE_REV}/{rel}", cached)
        patch = strip_tests(json.load(open(cached))[r["iid"]]["model_patch"] or "")
        if pid_of(r["iid"], r["writer"], patch) != r["pid"]:
            sys.exit(f"Lite patch does not match its id: {r['pid']}")
        r["patch"] = patch
        return os.path.getsize(cached)

    with cf.ThreadPoolExecutor(8) as ex:
        size = sum(ex.map(one, need))
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Downloaded from the other team's Lite run: {len(need)} patch files, {size / 1e6:.1f} MB")


def traced_run(log, script, argv):
    """Child process: run an analysis script as __main__, logging every file it opens or lists."""
    out = open(log, "a")

    def hook(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            out.write(os.path.abspath(os.fsdecode(args[0])) + "\n")

    sys.addaudithook(hook)
    sys.argv = [script] + argv
    sys.path.insert(0, os.getcwd())
    try:
        runpy.run_path(script, run_name="__main__")
    finally:
        out.flush()


def run_steps():
    traces = []
    for name, cmd in STEPS:
        t = time.time()
        log = os.path.join(BASE, "trace", name + ".log")
        traces.append(log)
        with open(os.path.join(OUT, name), "w") as stdout:
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "--traced", log] + cmd.split(),
                               cwd=os.path.join(WORK, "scripts"), stdout=stdout, stderr=subprocess.PIPE, text=True,
                               stdin=subprocess.DEVNULL)
        if p.returncode:
            sys.exit(f"{cmd} failed:\n{p.stderr[-1500:]}")
        print(f"  {cmd.split()[0]:34s} {time.time() - t:5.1f} s")
    return traces


def same_as_committed(name):
    new, old = os.path.join(OUT, name), os.path.join(ROOT, "scripts", "derived", name)
    if name.endswith(".txt"):  # the first line of each block prints a dict whose order changes between runs
        lines = lambda p: [l for l in open(p) if not l.startswith("==")]
        return lines(new) == lines(old)
    a, b = json.load(open(new)), json.load(open(old))
    if name.startswith("fresh_replication"):  # the committed file has extra sensitivity numbers added later
        return all(b["gemma4-31b"].get(k) == v for k, v in a["gemma4-31b"].items())
    if name.startswith("repair_trace_audit"):  # file hashes of the traces, whose released copies have paths removed
        a.pop("source_sha256"), b.pop("source_sha256")
    return a == b


def load(name):
    return json.load(open(os.path.join(OUT, name)))


def num(x, plus=True):
    s = f"{x:+.1f}" if plus else f"{x:.1f}"
    return s.replace("-", "−")


def ci(pair):
    return f"[{num(pair[0], False)}, {num(pair[1], False)}]"


def pct(x):
    return f"{round(x * 100)}%"


def includes_zero(pair):
    return pair[0] <= 0 <= pair[1]


def claims():
    """(section, what is claimed, text that must appear in paper/writeup.md or None for a figure, expected, recomputed)"""
    fresh = load("fresh_replication_2026-10-06.json")["gemma4-31b"]
    lite = load("third_party_lite_2026-11-01.json")["gemma4-31b"]
    lcb = load("lcb_judging_2026-11-01.json")["gemma4-31b"]
    other = load("other_models_heldout_2026-10-22.json")
    large = other["pooled"]
    sweep = load("lcb_sweep_2026-11-04.json")["models"]
    same = load("lcb_same_model_2026-11-05.json")
    belief = load("belief_vs_recognition_2026-11-03.json")
    sizes = load("gemma_sizes_2026-10-28.json")
    blind = load("lcb_blind_spot_2026-11-03.json")
    stamp = load("rubber_stamp_reasons_2026-10-22.json")
    think = load("thinking_mode_2026-10-22.json")["own_failing_100"]
    actor = load("judge_as_actor_2026-11-04.json")["gemma"]
    sft = load("sft_pilot_run2_2026-11-05.json")
    gate = load("existing_test_gate_2026-11-05.json")
    repair = load("test_repair_2026-11-05.json")
    audit = load("repair_trace_audit_2026-11-05.json")
    seeds = load("repair_seeds_2026-11-06.json")
    tie = load("tie_break_2026-10-22.json")
    counts = load("paper_counts_2026-11-05.json")
    script, sandbox, grading = counts["reproduction_script"], counts["sandbox_problem"], counts["grading_check"]
    mini_off = load("thinking_mode_2026-10-22.json")["own_failing_100"]["off"]
    strong = open(os.path.join(OUT, "strong_writer_leniency_2026-11-04.txt")).read()
    held, rest = strong.split("== lite:")
    grab = lambda text, key: re.search(rf"{key}: (\S+ \[.*?\])", text).group(1).replace("-", "−")

    answer = {}
    for tag in ("gemma4-31b", "glm-4.5"):
        for r in map(json.loads, open(os.path.join(WORK, "scripts", "derived", f"fresh_{tag}.jsonl"))):
            if r["pid"].startswith("matplotlib__matplotlib-24570|gemma-4-31b") and r.get("parsed") is not None:
                answer[tag] = r["parsed"]

    # Which held-back patches break a test that passes with the reference patch.
    gdir = os.path.join(WORK, "data", "lab-runs", "existing-test-gate")
    meta = {m["pid"]: m for m in map(json.loads, open(os.path.join(gdir, "meta.jsonl")))}
    runs = list(map(json.loads, open(os.path.join(gdir, "runs.jsonl"))))
    held_back = {r["pid"] for r in runs if r["kind"] == "patch" and r.get("decision") == "block"}
    witness = {p: t for w in runs if w["kind"] == "witness" for p, t in (w.get("tests") or {}).items()}
    real = lambda p: any(s == "PASSED" for s in witness.get(p, {}).values())
    stamped_failing = [p for p in held_back if meta[p]["writer"] == "gemma-4-31b" and meta[p]["y"] == 0
                       and meta[p]["gemma"] == 100]
    rdir = os.path.join(WORK, "data", "lab-runs", "test-repair", "tests")
    labels = {r["instance_id"]: r for r in map(json.loads, open(os.path.join(rdir, "labels.jsonl")))}
    harmed = [p for p in held_back if meta[p]["writer"] == "gemma-4-31b" and meta[p]["y"] == 1
              and labels.get(meta[p]["iid"], {}).get("resolved") is False]

    coders = [list(csv.DictReader(open(os.path.join(WORK, "data", "hand-codes", f"claims-coder-{c}.csv")))) for c in "ab"]
    endorsed = [sum(r["endorses_defect"] == "yes" for r in rows) for rows in coders]
    lenient = lambda m: sweep[m]["leniency_qwen_reference"]["ci95"][0] > 0
    small = ["gpt-oss-20b", "olmo-3.1-32b", "nemotron-nano-9b-v2", "seed-oss-36b", "gemma-4-12b", "gemma-4-26b-a4b"]
    judges = [m for m in blind if isinstance(blind[m], dict) and "blind_spot_effect" in blind[m]]
    own_stamped = sft["slices"]["own_stamped"]["measures"]
    n_stamped = sft["n"]["eval_own_stamped_failing"]
    calls = tie["tie_breaks"]["model_calls"]["accept_25"]
    t, r = repair["tests"], repair["review"]

    return [
        ("1", "matplotlib 24570: Gemma scores it 100, GLM-4.5 scores it 20", "scored the same patch 20", "100 and 20",
         f"{answer['gemma4-31b']} and {answer['glm-4.5']}"),
        ("2", "held-out issues and patches scored by all nine judges", "193 held-out issues", "193 issues",
         f"{gate['issues']} issues"),
        ("3.1", "failing patches Gemma scores 100", "52 of its 85 failing patches", "52 of 85",
         f"{stamp['own_failing_scored_100']} of {fresh['n']['own_failing']}"),
        ("3.1", "Figure 1a, scored 100, held-out: own, other writers", None, "61%, 35%",
         f"{pct(fresh['gemma4-31b_scored100_own_failing'])}, {pct(fresh['gemma4-31b_scored100_control_failing'])}"),
        ("3.1", "Figure 1a, scored 100, Lite: own, other writers", None, "63%, 40%",
         f"{pct(lite['gemma4-31b_scored100_own_failing'])}, {pct(lite['gemma4-31b_scored100_control_failing'])}"),
        ("3.1", "Figure 1a, scored 100, LiveCodeBench: own, other writers", None, "50%, 8%",
         f"{pct(lcb['gemma4-31b_scored100_own_failing'])}, {pct(lcb['gemma4-31b_scored100_control_failing'])}"),
        ("3.1", "above the outside judges, held-out: own failing, others' failing", "about 14 points above", "+14.1, −2.6",
         f"{num(fresh['lenient_raw_failing_own'])}, {num(fresh['lenient_raw_failing_control'])}"),
        ("3.1", "leniency, own minus others' failing, held-out", "16.6 points [10.3, 23.1]", "+16.6 [10.3, 23.1]",
         f"{num(fresh['lenient_raw_failing_difference'])} {ci(fresh['lenient_raw_failing_difference_ci95'])}"),
        ("3.1", "same difference, Lite and LiveCodeBench", "The same holds on Lite and LiveCodeBench",
         "+17.8, +23.0, both above zero",
         f"{num(lite['lenient_raw_failing_difference'])}, {num(lcb['lenient_raw_failing_difference'])}, "
         + ("both above zero" if min(lite['lenient_raw_failing_difference_ci95'][0],
                                     lcb['lenient_raw_failing_difference_ci95'][0]) > 0 else "NOT both above zero")),
        ("3.1", "matched on the outside judges' score, held-out", "still +13.6", "+13.6 [7.1, 20.3]",
         grab(held, "own_minus_others_matched_panel")),
        ("3.1", "five large models judging their own patches, pooled", "none shows extra trust like Gemma's", "+0.4 [−2.5, 3.4]",
         f"{num(large['lenient_difference_failing'])} {ci(large['lenient_difference_failing_ci95'])}"),
        ("3.1", "small open models lenient on LiveCodeBench", "five of six other usable small open models", "5 of 6",
         f"{sum(map(lenient, small))} of {len(small)}"),
        ("3.1", "Gemma 12B and 26B-A4B lenient too, 31B the largest", "Gemma 4 31B has the largest estimate", "yes",
         "yes" if lenient("gemma-4-12b") and lenient("gemma-4-26b-a4b") and
         sweep["gemma-4-31b (existing)"]["leniency_qwen_reference"]["value"] ==
         max(v["leniency_qwen_reference"]["value"] for v in sweep.values()) else "no"),
        ("3.1", "Figure 2, extra trust in own failing programs, seven models", None,
         "+40.3, +28.3, +26.0, +18.6, +13.4, +12.1, +4.2",
         ", ".join(num(x) for x in sorted((v["leniency_qwen_reference"]["value"] for k, v in sweep.items()
                                           if k not in ("glm-4-9b", "phi-4-mini")), reverse=True))),
        ("3.1", "models set aside: pass rates of GLM-4-9B and Phi-4-mini", "they pass almost no problems", "0.3%, 2.7%",
         f"{sweep['glm-4-9b']['pass_rate_292']:.1%}, {sweep['phi-4-mini']['pass_rate_292']:.1%}"),
        ("3.2", "same-edit patches get extra trust, Lite", "over the others is 20.0 points",
         "+20.0 [14.1, 25.9]",
         f"{num(belief['swe-bench-lite']['sim_effect'])} {ci(belief['swe-bench-lite']['sim_effect_ci95'])}"),
        ("3.2", "same test, held-out; the interval reaches zero", "and its interval reaches zero",
         "+8.0, reaches zero",
         f"{num(belief['held-out']['sim_effect'])}, "
         + ("reaches zero" if includes_zero(belief["held-out"]["sim_effect_ci95"]) else "above zero")),
        ("3.2", "no extra trust in own patch beyond same-edit patches, both sets", "We detect no extra trust", "both include zero",
         "both include zero" if includes_zero(belief["held-out"]["own_minus_same_ci95"]) and
         includes_zero(belief["swe-bench-lite"]["own_minus_same_ci95"]) else "not both"),
        ("3.2", "Gemma 12B and 26B-A4B on the 31B's failing patches", "neither shows measurable extra trust",
         "+0.4, +3.9, both include zero",
         f"{num(sizes['gemma4-12b_lenient_failing_difference'])}, {num(sizes['gemma4-26b-a4b_lenient_failing_difference'])}, "
         + ("both include zero" if includes_zero(sizes["gemma4-12b_lenient_failing_difference_ci95"]) and
            includes_zero(sizes["gemma4-26b-a4b_lenient_failing_difference_ci95"]) else "not both")),
        ("3.2", "Gemma on Claude 4 Sonnet's failing patches, Lite", "about as much as its own", "+1.7 [−5.3, 8.7]",
         grab(rest, "own_minus_strong")),
        ("3.3", "thinking before scoring: scored 100, on and off", "62% of its failing patches 100, against 61%", "62%, 61%",
         f"{pct(think['on'])}, {pct(think['off'])}"),
        ("3.3", "own reproduction script: last run ended without error", "in almost all failing runs", "58 of 64",
         f"{script['ended_without_error']} of {script['ran_own_script']}"),
        ("3.3", "shell judge: still 100 on stamped failing patches", "still scores 80% at 100", "80%",
         pct(actor["approval_100"]["own_fail"]["value"])),
        ("3.3", "its test fails without the patch and passes with it", "in most of them on failing", "61%",
         pct(actor["test"]["flag_share_own_fail"])),
        ("3.3", "shell lowers the score: failing, passing", "more often on failing patches", "20%, 5%",
         f"{pct(1 - actor['approval_100']['own_fail']['value'])}, {pct(1 - actor['approval_100']['own_pass']['value'])}"),
        ("3.3", "shell judge separates them slightly (AUROC)", "AUROC 0.58", "0.58", f"{actor['auroc_actor_own']['value']:.2f}"),
        ("3.3", "LoRA: accepted of 51, with adapter and without", "still accepts almost all", "48 and 50 of 51",
         f"{round(own_stamped['on']['false_accept'] * n_stamped)} and {round(own_stamped['off']['false_accept'] * n_stamped)} "
         f"of {n_stamped}"),
        ("3.3", "LoRA: change in false acceptance, in points", "did not reduce the failing", "−4.2 [−8.3, 0.0]",
         f"{num(sft['primary']['on']['false_accept_diff'] * 100)} "
         f"{ci([x * 100 for x in sft['primary']['on']['false_accept_diff_ci95']])}"),
        ("3.4", "existing-test check holds back Gemma's failing patches", "14 of all 26 held-back failing patches", "26 of 85",
         f"{gate['all_failing_gemma']['blocked']} of {gate['all_failing_gemma']['of']}"),
        ("3.4", "of the failing patches it scored 100", "15 of the 52 failing patches Gemma scored 100", "15 of 52",
         f"{gate['primary']['stamped_failing']['blocked']} of {gate['primary']['stamped_failing']['of']}"),
        ("3.4", "broken test passes with the reference patch", "In almost all of these", "14 of 15",
         f"{sum(map(real, stamped_failing))} of {len(stamped_failing)}"),
        ("3.4", "held-back failing repaired: tests shown, second look", "against 6 with a second look", "14, 6",
         f"{t['blocked_failing_now_passing']}, {r['blocked_failing_now_passing']}"),
        ("3.4", "repaired in only one condition: tests, second look", "against 6 with a second look", "8, 0",
         f"{repair['tests_vs_review']['tests_only']}, {repair['tests_vs_review']['review_only']}"),
        ("3.4", "one-sided sign test", "p = 0.004", "0.004", f"{repair['tests_vs_review']['sign_test_p']:.3f}"),
        ("3.4", "stamped failures repaired: tests shown, second look", "repairs 9 of its 52", "9, 3 of 52",
         f"{t['stamped_failing_now_passing']}, {r['stamped_failing_now_passing']} of {t['of_stamped_failing']}"),
        ("3.4", "correct stamped patches broken by the repair", "breaks\n4 of its 81", "4 of 81",
         f"{audit['arms']['tests']['stamped_harms']} of {gate['primary']['stamped_passing']['of']}"),
        ("3.4", "check holds back passing patches it scored 100", "about one in ten correct patches", "7 of 81",
         f"{gate['primary']['stamped_passing']['blocked']} of {gate['primary']['stamped_passing']['of']}"),
        ("3.4", "check holds back reference patches", "about one in ten correct patches", "18 of 193",
         f"{gate['primary']['reference']['blocked']} of {gate['primary']['reference']['of']}"),
        ("3.4", "the check alone by its plan", "too many to count the check alone as a fix", "too many false blocks",
         gate["reading"]),
        ("3.4", "broken test also fails with the reference, of 4 broken", "In 3 of the 4 correct patches", "3 of 4",
         f"{sum(not real(p) for p in harmed)} of {len(harmed)}"),
        ("3.4", "fewer failing patches among the 133 stamped", "so five fewer fail", "5",
         str(audit["arms"]["tests"]["stamped_repairs"] - audit["arms"]["tests"]["stamped_harms"])),
        ("3.4", "two more runs: stamped failures repaired with tests", "the tests repair eight", "8, 8",
         f"{seeds['seed1']['stamped_tests_repaired']}, {seeds['seed2']['stamped_tests_repaired']}"),
        ("3.4", "two more runs: correct stamped patches broken with tests", "break four", "4, 4",
         f"{seeds['seed1']['stamped_tests_broken']}, {seeds['seed2']['stamped_tests_broken']}"),
        ("3.4", "two more runs: stamped failures repaired by a second look", "repairs at most one", "1, 0",
         f"{seeds['seed1']['stamped_review_repaired']}, {seeds['seed2']['stamped_review_repaired']}"),
        ("4", "Llama-4-Maverick on its own contest programs: lenient", "finds Llama-4-Maverick lenient", "+19.1, lenient",
         f"{same['llama-4-maverick']['leniency_difference']:+.1f}, {same['llama-4-maverick']['reading']}"),
        ("4", "gpt-oss-120b on its own contest programs: not lenient", "gpt-oss-120b not", "+3.9, not lenient",
         f"{same['gpt-oss-120b']['leniency_difference']:+.1f}, {same['gpt-oss-120b']['reading']}"),
        ("4", "gpt-oss-120b and Llama-4-Maverick on their own held-out patches: intervals include zero",
         "we detect no extra trust", "+2.9 [−3.3, 8.8], +2.8 [−5.0, 10.8], both include zero",
         f"{num(other['gpt-oss-120b']['lenient_difference_failing'])} {ci(other['gpt-oss-120b']['lenient_difference_failing_ci95'])}, "
         f"{num(other['llama-4-maverick']['lenient_difference_failing'])} {ci(other['llama-4-maverick']['lenient_difference_failing_ci95'])}, "
         + ("both include zero" if includes_zero(other["gpt-oss-120b"]["lenient_difference_failing_ci95"])
            and includes_zero(other["llama-4-maverick"]["lenient_difference_failing_ci95"]) else "NOT both")),
        ("5", "rate scored 100 without the sandbox problem, Lite, Mini", "similar on the runs without this problem",
         "65%, 63%, 61%",
         f"{pct(sandbox['without_problem']['scored_100'] / sandbox['without_problem']['failing'])}, "
         f"{pct(lite['gemma4-31b_scored100_own_failing'])}, {pct(mini_off)}"),
        ("5", "grading check: official label kept", "26 of 30 other-writer patches", "26 of 30",
         f"{grading['official_label']} of {grading['patches']}"),
    ]


def main():
    started = time.time()
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.rmtree(os.path.join(BASE, "trace"), ignore_errors=True)
    for d in (WORK, OUT, os.path.join(BASE, "trace")):
        os.makedirs(d)
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(WORK, "scripts"), ignore=ignore)
    shutil.copytree(os.path.join(ROOT, "data"), os.path.join(WORK, "data"), ignore=ignore)

    pulled = pull_manifest()
    restore_lite_patches()
    print("Running the analyses:")
    traces = run_steps()

    opened = set()
    for log in traces:
        opened.update(l.strip() for l in open(log))
    unread = [p for p in pulled if os.path.abspath(os.path.join(WORK, p)) not in opened]
    identical = [n for n, _ in STEPS if same_as_committed(n)]

    paper = re.sub(r"\s+", " ", open(os.path.join(ROOT, "paper", "writeup.md")).read())
    rows, failed = claims(), 0
    print(f"\n{'Sec':4s} {'Claim':62s} {'Paper':30s} {'Recomputed':30s} Result")
    for sec, what, quote, want, got in rows:
        in_paper = quote is None or re.sub(r"\s+", " ", quote) in paper
        ok = want == got and in_paper
        failed += not ok
        result = "OK" if ok else ("NOT IN PAPER" if want == got else "DIFFERENT")
        print(f"{sec:4s} {what:62s} {want:30s} {got:30s} {result}")

    print(f"\n{len(rows) - failed} of {len(rows)} main-paper claims reproduced.")
    print(f"{len(identical)} of {len(STEPS)} recomputed summaries match the ones committed in scripts/derived/.")
    for n, _ in STEPS:
        if n not in identical:
            print(f"  differs: {n}")
    print(f"All {len(pulled)} downloaded files were read by an analysis." if not unread
          else f"Downloaded but not read: {unread}")
    print(f"Finished in {time.time() - started:.0f} s. Outputs are in .reproduce/out/.")
    sys.exit(1 if failed or unread else 0)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--traced"]:
        traced_run(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        main()
