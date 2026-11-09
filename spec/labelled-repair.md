# Spec: a repair told which broken tests are outdated, tested on other writers' held-back patches

Written 2026-11-07, before any labelling call or repair run on these patches. Plan and reasons:
`notes/method-labelled-repair-2026-11-07.md`. Terms follow `GLOSSARY.md`. Part 1 (labelling, no GPU) is approved by the
user ("check the parts that don't need a gpu"). Part 2 (repair runs, GPU) is not approved; it is fixed here so that its
reading cannot move after Part 1 is seen.

## Why

Section 3.3 of the paper shows that the repair with the broken tests shown fixes real regressions but obeys tests that
assert the old behavior, breaking correct patches. The exploratory rule (Gemma labels each broken test from the issue
and the test report; skip the repair when all are outdated) was designed and scored on the same 35 held-out and 44 Lite
Gemma patches (`notes/fable-rethink-fix-2026-11-07.md`). This tests the labelling, and then a repair that is told the
labels, on patches the rule never saw.

## Patches (fixed now, no outcome looked at)

The 194 patches from GLM-4.5, gpt-oss-120b, Kimi-K2, Llama-4-Maverick and Qwen3-Coder that the existing-test gate held
back on the held-out issues (`data/lab-runs/existing-test-gate/runs.jsonl`, decision "block"). Jobs:
`data/lab-runs/labelled-repair/jobs.jsonl`, built 2026-11-07 by `scripts/test_repair.py prepare --writers others` from
the gate's decisions and logs only (the same builder rebuilds the 35 Gemma jobs of `data/lab-runs/test-repair/` exactly).
123 of the 194 are on issues outside Gemma's 35 held-back issues (secondary set).

Truth for "outdated", fixed now: a patch is outdated-only when none of its broken tests passes once the reference patch
is applied instead (the gate's witness rows), and real regression otherwise. Counts known before this spec from the
witness and labels only: 37 outdated-only (24 correct, 13 failing), 157 real regression (22 correct, 135 failing).
Correct or failing: the official label in the gate's `meta.jsonl`.

## Part 1: labelling (no GPU)

- Prompt: `scripts/outdated_test_judge.py` as run on 2026-11-07 (file sha256 prefix `969b64606b60ad45`; an optional
  jobs-folder argument was then added, file `24d7490ed7337dfc`; the `prompt()` function, sha256 prefix
  `2b0444c9298bc4aa`, is byte-identical to the development script in `notes/fable-rethink-fix-2026-11-07/`): the issue
  and the broken-test report the repair agent would see, never the patch; per test OUTDATED or REGRESSION, and
  `all_outdated`. The Testora-style prompt named in the notes is not used: it has no development record, and choosing
  between two prompts on these patches would void the test.
- Model: hosted `google/gemma-4-31b-it` on OpenRouter through `selfjudge_matrix.call` (sha256 prefix
  `79ffb8735f42c492`): temperature 0, reasoning off, 1,200 output tokens, one call per patch. An unparsed answer is
  asked once more; a patch still unparsed counts as not all outdated (the repair goes ahead).
- Measures: share of the 37 outdated-only patches labelled all outdated (flag rate); share of the 157 real-regression
  patches labelled all outdated (wrong-flag rate); both again on the 123 secondary patches; per-test agreement with the
  witness where test names match.
- Development values (same prompt, same model): flag 5 of 8 held-out, 11 of 19 Lite; wrong flag 2 of 27 held-out, 6 of
  28 Lite. Prediction: flag rate about 60%, wrong-flag rate about 12%.
- Reading (stop rule 1):
  - flag rate at least 50% and wrong-flag rate at most 25%: Part 2 as written below;
  - otherwise, flag rate at least 40% and wrong-flag rate at most 35%: Part 2 without the keep branch (every
    held-back patch is repaired, with the labels shown);
  - otherwise: stop; Section 3.3 stays as it is and says the labelling did not carry over.
- Counterfactual readable without a GPU, reported whatever the reading: of the 46 correct patches, how many the keep
  branch would keep from the repair; of the 135 failing real-regression patches, how many it would keep unrepaired.

## Part 2: repair runs (GPU, needs the user's approval)

- Arms, every one of the 194 patches, one run each: (a) the repair with the broken tests shown, as in
  `spec/test-repair.md`; (b) the labelled repair: the same note, plus the list of tests Part 1 labelled outdated and the
  instruction to keep the issue's behavior over those tests, repair the others and not edit test files. Under the
  Part 1 reading with the keep branch, patches labelled all outdated are kept unrepaired in arm (b). Agent settings as in
  `spec/test-repair.md` (mini-SWE-agent 1.7.0, 4-bit Gemma, thinking off, step limit 50, temperature 0, the repository
  environment active). The note text for (b) is written and frozen before the first run.
- Readings from the same runs: no repair (start labels); Agentless-style skip (keep when all labelled outdated, else
  arm a); arm (b).
- Primary measure: net passing patches among the 194, arm (b) minus arm (a), 95% interval from 2,000 bootstrap
  resamples of issues. The method claim stands only if the interval is above zero and arm (b) also has more passing
  patches than no repair. Secondary: correct patches broken (of 46), failing patches repaired (of 148), the same on the
  123 secondary patches, and the Agentless-style skip against both.
- Stop rule 2: after the first 40 patches finish in both arms (20 outdated-only, 20 real regression, drawn now by seed
  0 from the jobs list), stop if arm (b) breaks more correct patches than arm (a) or repairs 3 or more fewer failing
  patches.
- Caveat fixed now: the agent repairs other writers' patches, not its own; all 194 come from SWE-bench Verified issues.

### Part 2 details, fixed 2026-11-07 after Part 1 and before any repair run

Part 1 gave "Part 2 as written" (`derived/labelled_repair_labels_2026-11-07.json`), so the keep branch stays.
`scripts/test_repair.py label` added arm (b) to the jobs (the jobs as prepared are kept as `jobs-unlabelled.jsonl`).
Revised the same evening after a code review, still before any repair run: a label now counts only for a test the
patch actually broke (two labels named tests from the log that did not break and were dropped: pytest-7324 Llama and
sympy-15349 Llama, which moved to the third group), and names keep the report's suffix. File hashes (sha256 prefix):
`scripts/test_repair.py` `f49b640ab0bb3b5a`, `scripts/labelled_repair_analyze.py` `053d59e81a15f488`,
`scripts/eval_apptainer.py` `c7f41a6f137372e8`, `scripts/lab/test_repair_chain.sh` `441bb2004d1f1f67`, `jobs.jsonl`
`aeda6510592d196d`. Each patch falls in one of three groups:

- **Keep (25):** labelled all outdated. Arm (b) keeps the start patch; no run.
- **Labelled (19):** at least one of the patch's broken tests labelled outdated, not all. Arm (b) runs with the note
  below.
- **Same as tests shown (150):** none of the patch's broken tests labelled outdated, or the answer did not parse (4).
  Arm (b)'s note would equal arm (a)'s, so arm (b) takes arm (a)'s run and grade; no second run. This removes
  run-to-run noise from the comparison on these patches, so the difference between the arms comes only from the 44
  patches the labels change.

Arm (b)'s note is arm (a)'s note with its last line ("Fix the patch so these tests pass again and the issue above stays
solved. Do not edit the test files.") replaced by:

```
Judged from the issue alone, these broken tests check old behaviour that the issue asks to change:
- <each test labelled OUTDATED, in the labeller's order>

For these tests, keep the behaviour the issue asks for, even if they still fail. Fix the patch so the other broken tests
pass again and the issue above stays solved. Do not edit the test files.
```

A labelled name counts when it matches exactly one of the patch's broken tests (exactly, or as its start before " ("
for Django names, which the labeller sometimes writes without the class); the note writes that test as the report
lists it, suffix included. A name that matches no broken test is left out.

GPU runs: arm (a) on 194 patches, arm (b) on 19. Order: first the 40 stop-rule-2 patches
(`data/lab-runs/labelled-repair/stop2_pids.txt`; 3 of them need an arm (b) run), grade them, apply stop rule 2
(`scripts/labelled_repair_analyze.py --stop2`), then the rest. Lab chain, with this `jobs.jsonl` copied into the run
folder first (the chain stops before starting the server if the jobs lack arm (b)):
`OUT=labelled-repair ARMS=tests,labelled RETRY_UNGRADED=1 PIDS_FILE=<stop2_pids.txt> bash scripts/lab/test_repair_chain.sh`,
then the same without `PIDS_FILE`.

How each run counts (`scripts/labelled_repair_analyze.py`):

- Submitted a non-empty patch with a grade: that grade.
- Submitted an empty patch (the agent undid the whole start patch): unresolved, as in the Lite repair analysis
  (`scripts/lite_repair.py`).
- Ended without submitting (step limit, context window): the start patch and its official grade.
- Server or sandbox error (vLLM RetryError, a sandbox that did not build, a start patch that did not apply): the run is
  redone when the chain is run again; no reading until it has been tried twice; if it fails twice, it counts as the start patch.
- Grading timeout: graded again (`--retry-ungraded`); no reading while any patch lacks a grade. Grading build error
  after a retry: the start patch and its official grade.

## Not to claim

- That the labelling idea is new (Agentless asks the model which passing tests should not be run; Testora classifies
  behavior changes as intended or unintended).
- Any result from Part 1 as a gain in resolved issues; Part 1 measures labels only.
- That a result on Verified carries to Lite, where development labelling was weaker.

## Addendum (2026-11-09, after the full repair run): Sphinx start patches had their fix removed

Written before any rerun. Full account: `spec/existing-test-gate.md`, addendum 2. Of the 27 Sphinx patches in the 194, 26
reached the agent with their source fix removed, and Gemma was told a patch had been applied. The other one has no source
file to apply. The gate decisions behind all 27 were made on unpatched code. Those 27 repair runs are invalid and are not
used. They stay on disk.

The new gate rows for the 68 affected patches decide the repair set. A patch of another writer whose new decision is
"block" enters the set and gets a run in the tests arm, with labels from the same labeller and prompt (arm (b) as in
Part 2). A patch whose new decision is "pass" or "no check" leaves the set and counts as its start patch. The analysis
script is otherwise unchanged. The file hashes of the changed scripts are recorded in the changelog entry of the rerun.
