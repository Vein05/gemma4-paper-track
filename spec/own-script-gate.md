# Spec: does Gemma's own reproduction script tell its passing patches from its failing ones?

Written 2026-11-03, before any script was run outside the agent's own trajectory. Exploratory, one set (held-out
issues); the Lite run's trajectories are not available. Proposed in `notes/committee-2026-11-03/fable_story.md` (D1);
approved by the user ("sure do it").

## Why

In most of Gemma's failing held-out runs, Gemma wrote a reproduction script, ran it after its edit, and the script
ended without error (`changelog/2026-11-03.md`: 79 of 98 failing runs added one, 73 ran it, 63 ended without error). A
script that ends without error after the edit tells the agent nothing unless it failed before the edit. If the scripts
that fail before and pass after mark the passing patches, an agent gets a free submit gate: no extra model call, only
two runs of a script the agent already wrote.

## Data

Gemma 4 31B's mini-SWE-agent runs on the held-out issues: `data/mcsr-runs/main-a/` and `main-b/` (200 trajectories,
`trajs/<iid>.json`; labels `labels.jsonl`). Analysis set: Gemma's 180 own patches in the paper's held-out analysis
(`fresh_judging.load`, paid panel), with the hosted Gemma's written score (`derived/fresh_gemma4-31b.jsonl`) and the
run's number of model calls (`n_calls`).

**The script.** The last command in the trajectory that runs `python <file>.py` (not `-m`, not `-c`), skipping
scripts whose name starts with fix, modify, apply, patch, update, edit, change, replace or rewrite (they edit the source;
running one "before" would apply the fix). Added while preparing the jobs, before any run. The file must be
an added file in Gemma's final patch (true in 153 of the 161 runs that ran a script); otherwise the run is "no script".
Working directory: `/testbed`, or the directory of a `cd` earlier in the same command.

## Runs (MCSR Magnolia, CPU partition; no GPU)

One Apptainer sandbox per issue from its SWE-bench image, as in `scripts/eval_apptainer.py`. Same exec settings as the
agent (`--contain --cleanenv --writable`, mini-SWE-agent's SWE-bench environment variables). Three conditions, the
repository reset (`git checkout -- . && git clean -fdq`) between them:

1. **Before**: only the added files of Gemma's patch applied (the script and its helpers; no change to existing files).
2. **After**: Gemma's full patch applied.
3. **Reference**: the SWE-bench reference patch plus Gemma's added files.

`python <script>`, 120 s limit. A run **passes** if the exit code is 0 and the output has no "Traceback" and no
"AssertionError"; otherwise it **fails** (time-outs fail). Script `scripts/own_script_gate.py`; outputs
`data/mcsr-runs/own-script-gate/runs.jsonl` (one line per issue and condition, with exit code and the last 3,000
characters of output).

Classes per patch: **reproduced and fixed** (fails before, passes after); passes both; fails both; passes before,
fails after; no script.

## Measures

1. **Primary, the gate as a tie-break.** Rank Gemma's 180 own patches by Gemma's written score, then "reproduced and
   fixed" first, then fewer model calls. Share passing in the top quarter (45 patches), against 78% for Gemma's score
   with fewer model calls only (paper, Section 3.2). Paired bootstrap of the difference, 2,000 resamples of patches
   (one patch per issue), seed 0.
2. **The gate as a filter.** Among Gemma's patches scored 100: pass rate of "reproduced and fixed" patches against the
   rest; the share of Gemma's 100s it keeps.
3. **Description.** Class counts among Gemma's failing and passing patches. Share of scripts that also fail with the
   reference patch (the script tests something the issue does not ask for). Share of scripts with an `assert`,
   `raise` or `sys.exit` (a script that only prints passes whatever the code does).

## Reading, fixed now

- **The gate works:** the top quarter passes at least 86% and the interval of the gain over fewer model calls is above
  0. The paper offers the gate as a method for agents, on one set, as exploratory.
- **The scripts never reproduced the bug:** if most stamped failing patches pass before, the paper says Gemma's own
  check was empty (the script passed without the fix) and reports the share.
- **The scripts test the wrong thing:** if most stamped failing patches are "reproduced and fixed" yet fail the hidden
  tests, the paper says Gemma's scripts check the behaviour it imagined, not the issue's, and reports the share that
  also fails with the reference patch.
- Otherwise: description only, in the supplement.

## Logging

Changelog entry; W&B group `own-script-gate`; outputs copied back to `data/mcsr-runs/own-script-gate/`; analysis
`scripts/derived/own_script_gate_2026-11-03.json`.
