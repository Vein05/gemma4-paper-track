# Spec: does running the repository's existing tests catch the failing patches Gemma scores 100?

Written 2026-11-05, before any test of this gate was run. Exploratory: the held-out issues have been inspected
many times. Requested by the user ("fixes is preferred in the abstract"), after the label-assisted count below.

## Why

SWE-bench's own grading shows that 17 of the 52 failing held-out patches Gemma scored 100 break an existing test
that should still pass (`scripts/derived/test_flag_2026-11-02.json`, `scripts/derived/regression_gate_inventory_2026-11-05.json`).
That count uses the benchmark's PASS_TO_PASS list, which is chosen with the reference patch, so it is an upper bound,
not something an agent can do. This spec tests the version an agent can do: pick the tests from the changed code
alone, run them before and after the patch, and block the patch if a test that passed before now fails.

The gate sets Gemma's score aside, like the tie-break and the second judge (`paper/new-evidence-2026-11-03.md`,
section 3b). If it works, it is a fix for the agent's submit check, not for Gemma's judgment.

## Patches

The paper's held-out analysis set: the 957 patches scored by all nine judges (`fresh_judging.load`, runs `main-a` and
`main-b`): Gemma's 180 (85 failing, 95 passing; 52 failing and 81 passing scored 100 by Gemma) and the five other
writers' 777, each as the judges saw it (test files removed by `strip_tests`). Plus the SWE-bench reference patch of
every issue in the set, as a passing control. Labels: our grading for Gemma's patches, official labels for the others,
reference patches count as passing.

## The gate (fixed now; no change after any outcome is seen)

Script `scripts/existing_test_gate.py`. Nothing below reads PASS_TO_PASS, FAIL_TO_PASS, the test patch, the reference
patch or any label.

1. **Changed source files.** Files the patch modifies that exist at the base commit, end in `.py`, and are not test
   files. A test file has a path component `tests`, `test` or `testing`, or a name `test_*.py`, `*_test.py`,
   `tests.py` or `conftest.py`.
2. **Changed names.** Parse each changed file at base with `ast`. For every base line the patch removes or changes,
   and for the base line before each pure insertion, take the innermost enclosing function and class. Keep names of
   at least 4 characters that are not dunder names (a dunder method contributes its class). A change outside any
   function or class contributes the module name.
3. **Candidate tests.** The test files tracked by git at base whose name is `test_*.py`, `*_test.py` or `tests.py`.
   Score each: 100 if its name is `test_<module>.py` or `<module>_test.py` for a changed module (`__init__.py` counts
   as its package's name); plus 10 for each changed name that appears in it as a whole word; plus 1 if it contains the
   changed module's dotted path (path without `.py`, `/__init__` and a leading `src/` or `lib/`, slashes as dots).
   Keep the files scoring at least 10, best 4 by score (ties: shorter path, then
   alphabetical). If none scores 10, keep up to 2 files scoring at least 1. If none, the patch has **no check**.
4. **Runs.** One Apptainer sandbox per issue from its SWE-bench image (as in `scripts/eval_apptainer.py`, with the
   `testbed` environment activated). The repository's SWE-bench test command (`MAP_REPO_VERSION_TO_SPECS[repo][version]
   ["test_cmd"]`) with the selected files as arguments (Django: as module labels, the transform of SWE-bench's
   `get_test_directives`). Results parsed with SWE-bench 4.1.0's log parser for the repository.
   - **Base:** each file selected for any patch of the issue, run on its own on the unpatched repository, twice. A
     test is *stable at base* if it passes both times.
   - **Patch:** apply the patch (SWE-bench's three apply fallbacks), run the repository's SWE-bench install command
     (as the official grading does), run that patch's selected files. If a test stable at base is FAILED or ERROR,
     run the patch's selected files once more.
   - Between patches: `git checkout -- .`, remove files that were not untracked at base.
   - Time limits: 20 minutes per test run, 2 hours per issue.
5. **Decision.** **Block** if at least one test stable at base fails in both patch runs. A test fails if the parser
   reports it FAILED or ERROR, or if it is missing from the run (a patch that breaks importing a module removes its
   tests); blocks are reported by these two reasons. **Pass** otherwise.
   **No check** when no file is selected, no selected test is stable at base, the patch does not apply, the sandbox
   does not build, or a run times out or cannot be parsed. No check counts as not blocked.

## Measures

Intervals: 2,000 bootstrap resamples of issues, seed 0.

1. **Primary: catch and false block.** Of the 52 failing patches Gemma scored 100, the number blocked (no check
   counts as not caught). Of Gemma's passing patches, the number blocked: of the 81 scored 100 and of all 95. Of the
   reference patches, the number blocked.
2. Coverage: the share of patches with a check, by writer and repository; the reasons for no check.
3. **Named secondaries.**
   a. Overlap with the label-assisted 17: how many of them the gate blocks, and how many blocks are outside them.
   b. Witness check, offline: for each blocked patch, run its failing tests' files with the reference patch applied
      in the same sandbox; does the failing test pass there? (Run after all decisions; never changes a decision.)
   c. Other writers' failing patches that Gemma scored 100: share blocked, against Gemma's own.
   d. Gate or GLM-4.5 (50 or less) on the 52 and on the 81 (GLM-4.5 was chosen after its scores were seen; exploratory).
   e. Top quarter: rank Gemma's 180 patches by not blocked, then Gemma's score, then fewer model calls; share passing
      in the top 45, against 78% for the paper's tie-break.
4. Cost: CPU-hours and wall time, per issue and in total.

## Reading, fixed now

- **The gate works:** at least 11 of the 52 (21%) blocked, at most 4 of the 81 passing patches scored 100 blocked,
  and at most 5% of the reference patches blocked. The abstract and the paper may then state a fix for an agent built
  on Gemma: run the existing tests of the changed code before submitting. One set, exploratory.
- **Partial:** 6 to 10 of the 52 blocked with the same false-block limits. The paper reports it in the results, not
  as a fix in the abstract.
- **Too many false blocks:** more than 4 of the 81 or more than 5% of the reference patches blocked. The gate is not
  offered; report why (old tests asserting behaviour the issue changes, or environment failures).
- **No fix:** fewer than 6 blocked.

Whatever the reading, the paper does not say the gate fixes Gemma's judgment, and does not call regression testing new.

## Run

Lab server, CPU only (no GPU): images already in `<workdir>/swe-env/sif`. Smoke test on 3 issues from three
repositories first, read for infrastructure only (sandbox, apply, install, test run, parse); the rule above does not
change after it except to fix a crash or a parser error, which goes in an addendum before the full run.

## Logging

Changelog entry with start, end and CPU-hours; W&B group `existing-test-gate` (logged from the Mac); outputs in
`data/lab-runs/existing-test-gate/`; analysis `scripts/derived/existing_test_gate_2026-11-05.json`.

## Addendum 1 (2026-11-05, after the smoke test, before the full run): run shape only

The smoke test (django__django-10999, sympy__sympy-12419, matplotlib__matplotlib-13989) showed that a sympy test's
result depends on which test files share one process: sympy's `collections` deprecation warning is raised as an
error at the first place that triggers it in a process, so a test can pass when its file runs alone and fail when
another file runs first. The base runs ran each file alone, the patch runs ran the files together, and the
reference patch was blocked by `test_sympy__series__fourier__FourierSeries`, a test its change does not touch.
Changes, to make base and patch runs the same shape:

1. Patch runs, reruns and the witness check run each selected file in its own process, as the base runs do. Tests
   are keyed by file and name. The rerun covers only the files holding a broken test.
2. The repository's install command also runs once before the base runs, so base and patch runs see the same
   installation.

The selection rule, the decision rule and the readings are unchanged. The django reference patch's block in the smoke
test (`test_negative` asserts the negative-duration behaviour the issue changes) is a real outcome of the rule and
stays. The smoke issues are rerun in the full run with the corrected code.
