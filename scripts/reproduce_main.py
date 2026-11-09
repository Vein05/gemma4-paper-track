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
HF_REV = "2be7dd2255cd560e42d8c9838a2ff23852c1e240"
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
    ("writer_table_2026-11-07.json", "writer_table.py"),
    ("failure_types_2026-11-07.json", "failure_types.py analyze"),
    ("nonpython_2026-11-07.json", "nonpython_analyze.py"),
    ("lite_repair_2026-11-07_empty-as-failing.json", "lite_repair.py analyze"),
    ("outdated_tests_2026-11-07.json", "outdated_tests.py"),
    ("labelled_repair_2026-11-09.json", "labelled_repair_analyze.py --no-wandb"),
    ("matched_writers_2026-11-09.json", "matched_writers.py analyze"),
    ("matched_writers_split_2026-11-09.json", "matched_writers_split.py"),
]
# The paper whose claims are checked: paper/writeup.md by default; REPRODUCE_PAPER selects another copy of its text.
PAPER = os.environ.get("REPRODUCE_PAPER", "paper/writeup.md")


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
    """Claims of paper/writeup.md: (section, what, quote that must appear in the paper or None, paper value,
    recomputed value)."""
    fresh = load("fresh_replication_2026-10-06.json")["gemma4-31b"]
    sizes = load("gemma_sizes_2026-10-28.json")
    belief = load("belief_vs_recognition_2026-11-03.json")
    stamp = load("rubber_stamp_reasons_2026-10-22.json")
    think = load("thinking_mode_2026-10-22.json")["own_failing_100"]
    actor = load("judge_as_actor_2026-11-04.json")["gemma"]
    sft = load("sft_pilot_run2_2026-11-05.json")
    gate = load("existing_test_gate_2026-11-05.json")
    repair = load("test_repair_2026-11-05.json")
    script = load("paper_counts_2026-11-05.json")["reproduction_script"]
    wt = load("writer_table_2026-11-07.json")
    ft = load("failure_types_2026-11-07.json")
    npy = load("nonpython_2026-11-07.json")
    lite = load("lite_repair_2026-11-07_empty-as-failing.json")
    labelled = load("labelled_repair_2026-11-09.json")
    strong = open(os.path.join(OUT, "strong_writer_leniency_2026-11-04.txt")).read()
    held, rest = strong.split("== lite:")
    grab = lambda text, key: re.search(rf"{key}: (\S+ \[.*?\])", text).group(1)  # ASCII minus, as in the draft
    sgn = lambda x: f"{x:+.1f}"
    ci_ = lambda v, c: f"{v:+.1f} [{c[0]:.1f}, {c[1]:.1f}]"
    net = lambda x: f"{x:+d}".replace("-", "−")
    answer = {}
    for tag in ("gemma4-31b", "glm-4.5"):
        for r in map(json.loads, open(os.path.join(WORK, "scripts", "derived", f"fresh_{tag}.jsonl"))):
            if r["pid"].startswith("matplotlib__matplotlib-24570|gemma-4-31b") and r.get("parsed") is not None:
                answer[tag] = r["parsed"]
    W = wt["per_writer"]
    others = [w for w in W if w != "gemma-4-31b"]
    weak = ["gpt-oss-120b", "llama-4-maverick"]
    E = ft["held_out_own_failing"]["types"]
    C = ft["held_out_own_failing_by_check"]
    L_t, L_l = labelled["all"]["tests"], labelled["all"]["labelled"]
    t, r = repair["tests"], repair["review"]
    lt, lr = lite["tests"], lite["review"]
    m = load("matched_writers_2026-11-09.json")["gemma4-31b"]
    sel = json.load(open(os.path.join(WORK, "scripts", "derived", "matched_writers_selection.json")))
    M = m["per_writer"]
    eq = lambda key: m[f"extra_trust_own_minus_matched_{key}"]
    top = lambda w: round(M[w]["gemma_share_100"] / 100 * M[w]["failing"]) / M[w]["failing"]  # share from the count
    fams = sorted({M[w]["family"] for w in m["band_writers"]})
    theirs = sum(sum(top(w) for w in m["band_writers"] if M[w]["family"] == f) /
                 sum(M[w]["family"] == f for w in m["band_writers"]) for f in fams) / len(fams)
    table1 = lambda w, name: (f"| {name} | {pct(M[w]['resolve_rate'])} | {pct(top(w))} | {num(M[w]['extra_trust'])} |")
    rows1 = [("20250726_mini-v1.0.0_o3-2025-04-16", "o3", "| o3 | 62% | 55% | −1.7 |"),
             ("glm-4.5", "GLM-4.5", "| GLM-4.5 | 61% | 57% | +3.8 |"),
             ("20260217_mini-v2.0.0_gpt-5-mini", "GPT-5 mini", "| GPT-5 mini | 59% | 79% | +3.0 |"),
             ("kimi-k2", "Kimi-K2", "| Kimi-K2 | 59% | 55% | +6.4 |"),
             ("20250726_mini-v1.0.0_gemini-2.5-pro", "Gemini 2.5 Pro", "| Gemini 2.5 Pro | 55% | 65% | +12.6 |"),
             ("gemma-4-31b", "Gemma 4 31B", "| Gemma 4 31B | 54% | 59% | +13.3 |"),
             ("20250807_mini-v1.7.0_gpt-5-nano", "GPT-5 nano", "| GPT-5 nano | 48% | 26% | −12.1 |"),
             ("20250726_mini-v1.0.0_o4-mini-2025-04-16", "o4-mini", "| o4-mini | 48% | 41% | −7.4 |")]
    return [
        ("Abs", "equally strong writers by the rule (within 8 points of Gemma)", "Against seven writers as strong as Gemma",
         "7", str(len(sel["band_writers"]))),
        ("1", "matplotlib 24570: Gemma scores it 100, GLM-4.5 scores it 20", "scored the same patch 20", "100 and 20",
         f"{answer['gemma4-31b']} and {answer['glm-4.5']}"),
        ("1", "extra trust in own failing patches, all other writers", "16.3 points further above", "+16.3",
         sgn(fresh["lenient_raw_failing_difference"])),
        ("1", "scored 100: Llama-4-Maverick's failing patches, Gemma's own", "the weakest writer's a quarter as often",
         "16%, 60%", f"{pct(W['llama-4-maverick']['gemma_100'])}, {pct(W['gemma-4-31b']['gemma_100'])}"),
        ("1", "extra trust: mixed-strength writers, equally strong writers",
         "is 16.3 points against five writers of mixed strength and 8.7 against seven", "+16.3, +8.7",
         f"{grab(held, 'own_minus_others').split()[0]}, {sgn(eq('family_balanced')['value'])}"),
        ("1", "equally strong writers, in the introduction", "the gap is 8.7 points", "+8.7 [1.7, 15.8]",
         ci_(eq("family_balanced")["value"], eq("family_balanced")["ci95"])),
        ("1", "correct held-back Lite patches broken with the tests shown", "On Lite it breaks 12 of 14 correct",
         "12 of 14", f"{lt['blocked_passing_now_failing']} of {lite['blocked_passing']}"),
        ("2", "held-out issues", "193 held-out issues", "193", str(gate["issues"])),
        ("2", "Go, Ruby and PHP issues run", "Gemma on 120 Go", "120", str(npy["issues_run"])),
        *[("3.1", f"Table 1, {name}", quote, quote, table1(w, name)) for w, name, quote in rows1],
        ("3.1", "equally strong writers: extra trust, share of the mixed-strength gap, interval",
         "is 8.7 points, about half of the gap above, with a 95% interval above zero", "+8.7, 53%, above zero",
         f"{sgn(eq('family_balanced')['value'])}, "
         f"{pct(eq('family_balanced')['value'] / float(grab(held, 'own_minus_others').split()[0]))}, "
         + ("above zero" if eq("family_balanced")["ci95"][0] > 0 else "reaches zero")),
        ("3.1", "scored 100: own failing, equally strong writers' failing (families weighted equally)",
         "100 to 59% of its own failing patches and to 57% of theirs, a difference within noise", "59%, 57%, includes zero",
         f"{pct(top('gemma-4-31b'))}, {pct(theirs)}, "
         + ("includes zero" if includes_zero(m["share_100_own_minus_matched_family_balanced"]["ci95"]) else "excludes zero")),
        ("3.1", "OpenAI writers among the seven; model families", "Four of the seven are OpenAI models", "4 of 7, 4 families",
         f"{sum(M[w]['family'] == 'gpt-oss' for w in m['band_writers'])} of {len(m['band_writers'])}, {len(fams)} families"),
        ("3.1", "above outside judges: Gemini 2.5 Pro's failing patches, Gemma's own", "as far above the outside judges as its own",
         "+12.6, +13.3", f"{sgn(M['20250726_mini-v1.0.0_gemini-2.5-pro']['extra_trust'])}, {sgn(M['gemma-4-31b']['extra_trust'])}"),
        ("3.1", "without Gemini; without the OpenAI writers", "without the OpenAI writers its interval includes zero",
         "+11.4, +5.7 includes zero", f"{sgn(eq('without_google')['value'])}, {sgn(eq('without_gpt-oss')['value'])} "
         + ("includes zero" if includes_zero(eq("without_gpt-oss")["ci95"]) else "excludes zero")),
        ("3.1", "two weakest writers' share of other writers' failing patches", "these two supply most of the group's",
         "59%", pct(sum(W[w]["failing"] for w in weak) / sum(W[w]["failing"] for w in others))),
        ("3.1", "scored 100, two weakest writers", "a quarter or less of the two weakest writers'", "25%, 16%",
         ", ".join(pct(W[w]["gemma_100"]) for w in weak)),
        ("3.1", "Figure 1b, held-out: mixed-strength, equally strong, without Gemini, without OpenAI", None,
         "+16.3 [9.9, 22.7], +8.7 [1.7, 15.8], +11.4 [4.1, 18.8], +5.7 [-1.6, 13.3]",
         f"{grab(held, 'own_minus_others')}, " + ", ".join(ci_(eq(k)["value"], eq(k)["ci95"])
                                                           for k in ("family_balanced", "without_google", "without_gpt-oss"))),
        ("3.1", "Figure 1b, Lite: mixed-strength writers", None, "+17.8 [12.1, 23.5]", grab(rest, "own_minus_others")),
        ("3.2", "Figure 1b and text, Go, Ruby and PHP", "its extra trust in its own is within noise", "+4.2 [-3.7, 11.8]",
         ci_(npy["estimates"]["extra_trust"]["value"], npy["estimates"]["extra_trust"]["ci95"])),
        ("3.2", "Go/Ruby/PHP: other writers solving at least as many issues as Gemma", "every other writer solves more issues than Gemma",
         "4 of 4", f"{sum(v >= npy['solved']['gemma-4-31b'] for k, v in npy['solved'].items() if k != 'gemma-4-31b')}"
                   f" of {len(npy['solved']) - 1}"),
        ("3.2", "Go/Ruby/PHP scored 100: own failing, other writers' failing", "Gemma gives 100 to 76% of", "76%, 68%",
         f"{pct(npy['estimates']['stamp_own']['value'])}, {pct(npy['estimates']['stamp_controls']['value'])}"),
        ("3.2", "Go/Ruby/PHP outside judges score own failing 100", "only 29% of the time", "29%",
         pct(npy["estimates"]["outside_stamp_own"]["value"])),
        ("3.2", "Gemma's failing held-out patches: wrong fix, regression only, both",
         "52 are wrong fixes, in which every existing test still passes. The other 30 break an existing test.", "82: 52, 13, 17",
         f"{ft['held_out_own_failing']['n']}: {E['wrong fix']['n']}, {E['regression']['n']}, {E['both']['n']}"),
        ("3.2", "thinking before scoring: scored 100, on and off", "62% of its failing patches 100, against 61%",
         "62%, 61%", f"{pct(think['on'])}, {pct(think['off'])}"),
        ("3.2", "own reproduction script: last run ended without error", "in almost all failing runs", "55 of 61",
         f"{script['ended_without_error']} of {script['ran_own_script']}"),
        ("3.2", "shell judge: failing patches it had scored 100, still 100", "on the 49 failing held-out patches",
         "49, 79%", f"{stamp['own_failing_scored_100']}, {pct(actor['approval_100']['own_fail']['value'])}"),
        ("3.2", "LoRA: accepted of 50, with adapter and without", "still accepts almost all", "47 and 49 of 50",
         f"{round(sft['slices']['own_stamped']['measures']['on']['false_accept'] * sft['n']['eval_own_stamped_failing'])}"
         f" and {round(sft['slices']['own_stamped']['measures']['off']['false_accept'] * sft['n']['eval_own_stamped_failing'])}"
         f" of {sft['n']['eval_own_stamped_failing']}"),
        ("3.3", "held-out repair: tests shown, second look, of held-back failing", "repairs 14 of the 26 held-back failing",
         "14, 7 of 26", f"{t['blocked_failing_now_passing']}, {r['blocked_failing_now_passing']} of {repair['blocked_failing']}"),
        ("3.3", "Lite repair with the tests shown, stable grades", "fixed 1 of 30", "1 of 30",
         f"{lt['blocked_failing_now_passing_stable']} of {lite['blocked_failing']}"),
        ("3.3", "Table 3, held-back failing patches", "| Held-back failing patches | 26 | 26 | 30 | 30 |", "26, 30",
         f"{repair['blocked_failing']}, {lite['blocked_failing']}"),
        ("3.3", "Table 3, held-back failing that break a listed test", "| Of these, break an existing test | 22 | | 15 | |",
         "22 of 26, 15 of 30", f"{ft['held_out_held_back_failing']['break_other_test']} of {ft['held_out_held_back_failing']['with_log']}, "
                               f"{ft['lite_held_back_failing']['break_other_test']} of {ft['lite_held_back_failing']['with_log']}"),
        ("3.3", "Table 3, repaired", "| Repaired | 14 | 7 | 1 | 0 |", "14, 7, 1, 0",
         f"{t['blocked_failing_now_passing']}, {r['blocked_failing_now_passing']}, "
         f"{lt['blocked_failing_now_passing_stable']}, {lr['blocked_failing_now_passing_stable']}"),
        ("3.3", "Table 3, held-back correct patches", "| Held-back correct patches | 9 | 9 | 14 | 14 |", "9, 14",
         f"{repair['blocked_passing']}, {lite['blocked_passing']}"),
        ("3.3", "Table 3, broken by the repair", "| Broken by the repair | 4 | 1 | 12 | 2 |", "4, 1, 12, 2",
         f"{t['blocked_passing_now_failing']}, {r['blocked_passing_now_failing']}, "
         f"{lt['blocked_passing_now_failing']}, {lr['blocked_passing_now_failing']}"),
        ("3.3", "Table 3, net change", "| Net change in passing patches | +10 | +6 | −11 | −2 |", "+10, +6, −11, −2",
         ", ".join(net(a["blocked_failing_now_passing" + s] - a["blocked_passing_now_failing"])
                   for a, s in ((t, ""), (r, ""), (lt, "_stable"), (lr, "_stable")))),
        ("3.3", "Lite: reference patch also held back, of held-back correct", "For all 14 correct Lite patches", "14 of 14",
         f"{lite['held_back_passing_reference_also_held_back']} of {lite['blocked_passing']}"),
        ("3.3", "Lite: correct patches broken, tests shown and second look", "broke 12 of these 14 patches when shown",
         "12, 2 of 14", f"{lt['blocked_passing_now_failing']}, {lr['blocked_passing_now_failing']} of {lite['blocked_passing']}"),
        ("3.3", "held-out resolved after the repair, before, of patches", "108 of Gemma's 180 patches pass after it, against 98",
         "108, 98 of 180", f"{t['resolved_after']}, {repair['resolved_before']} of {repair['gemma_patches']}"),
        ("3.3", "check holds back: own failing that break a listed test, wrong fixes",
         "holds back 22 of Gemma's 30 failing held-out patches that break a listed test, and only 4 of its 52 wrong fixes",
         "22 of 30, 4 of 52",
         f"{C['regression | block'] + C['both | block']} of {E['regression']['n'] + E['both']['n']}, "
         f"{C['wrong fix | block']} of {E['wrong fix']['n']}"),
        ("3.3", "labelled repair against tests shown: correct broken, fewer repaired",
         "Correct patches broken fell from 20 to 7, but fewer failing patches were repaired",
         "20 to 7, 5 fewer", f"{L_t['correct_broken']} to {L_l['correct_broken']}, "
                             f"{L_t['failing_repaired'] - L_l['failing_repaired']} fewer"),
        ("3.3", "labelled repair: net gain in passing patches, interval reaches zero", "the net gain is within noise",
         "+8, reaches zero", f"{net(labelled['labelled_minus_tests']['diff'])}, "
                             + ("reaches zero" if includes_zero(labelled["labelled_minus_tests"]["ci95"]) else "excludes zero")),
        ("5", "correct patches the repair's harm rests on", "rests on 23 correct patches", "23",
         str(repair["blocked_passing"] + lite["blocked_passing"])),
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

    paper = re.sub(r"\s+", " ", open(os.path.join(ROOT, PAPER)).read())
    rows, failed = claims(), 0
    print(f"\nChecking the claims of {PAPER}.")
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
