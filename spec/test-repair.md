# Spec: can Gemma repair the patches the existing-test gate blocks?

Written 2026-11-05, while the existing-test gate (`spec/existing-test-gate.md`) was running and before any of its
decisions were read. The user asked to "see how many of those 50 we could fix" and approved running more on the lab
A100 overnight. Exploratory, one set.

## Question

When the gate blocks one of Gemma's patches, an agent can show Gemma the tests that broke and let it try again. Does
that turn failing patches into passing ones, and is it the failing tests that help, or only a second look?

## Patches (rule fixed now; uses gate decisions only, no labels)

Every one of Gemma 4 31B's 180 held-out patches that the gate blocks, failing or passing by the official grade.
Start state: the issue's SWE-bench sandbox with that patch applied as uncommitted changes (the version the gate ran:
test files removed).

## Two arms, same budget

Gemma 4 31B (`google/gemma-4-31B-it-qat-w4a16-ct`, revision 52f3f65b), served by vLLM on the lab A100, temperature 0,
thinking off, in mini-SWE-agent 1.7.0 with its SWE-bench config, as in the writer runs, except: the repository's
`testbed` environment is active (the writer runs lacked it, `paper/new-evidence-2026-11-03.md` section 4h), the step
limit is 50, the context limit 65,536 tokens (shared GPU). The task is the issue text followed by one note:

- **Failing tests shown:** "A patch for this issue has already been applied to the repository (see `git diff`).
  Running the repository's existing tests shows that the patch breaks tests that passed before it:" then, per test
  file with a broken test, the command that runs it, the broken test names (at most 15) and the last 80 lines of its
  output (at most 4,000 characters); then "Fix the patch so these tests pass again and the issue above stays solved.
  Do not edit the test files."
- **Second look:** "A patch for this issue has already been applied to the repository (see `git diff`). It may
  contain mistakes or break existing behaviour. Check it and fix any problem you find, keeping the issue above
  solved. Do not edit the test files."

The submitted patch (mini-SWE-agent's `git diff` of the repository, so the original patch plus the edits) is graded
with `scripts/eval_apptainer.py` (SWE-bench's grading code, hidden tests). A run that does not submit keeps the
original patch and its original grade.

## Measures

1. **End to end, the user's question:** of the 52 failing patches Gemma scored 100, how many pass after gate plus
   repair with the failing tests shown (unblocked ones keep their failing grade). Same for the second-look arm.
2. **Primary comparison:** among blocked failing patches, passes after repair, failing tests shown against second
   look; exact one-sided sign test on the discordant issues.
3. **Harm:** among blocked passing patches, how many fail after repair, per arm.
4. Gemma's resolved count on the 180 issues before and after gate plus repair, per arm.
5. Cost: GPU-hours (start, end), calls and tokens per run.

## Reading, fixed now

- **The failing tests help repair:** more blocked failing patches pass with the failing tests shown than with a second
  look, sign test p < 0.05. The paper may say that an agent can turn N of the 52 into passing patches by running the
  existing tests and showing Gemma what broke.
- **A second look is enough:** both arms repair a similar number (p ≥ 0.05) and the second look repairs at least as
  many. The paper credits the gate, not the test output, for any repairs.
- **No repair:** fewer than 3 blocked failing patches pass in the failing-tests arm. The paper reports the gate as a
  check only.
- Otherwise (more repairs with the failing tests shown, p ≥ 0.05): counts only, no credit to the test output.

## Run and logging

Lab A100, shared with another user's jobs (about 23 to 37 GB in use at planning time): vLLM at 0.45 GPU memory.
Chain `scripts/lab/test_repair_chain.sh`: prepare jobs from the gate's outputs, serve, run both arms (8 workers), stop
the server, grade both arms on CPU. Changelog with start, end and GPU-hours; compute ledger; W&B group `test-repair`;
outputs in `data/lab-runs/test-repair/`; analysis `scripts/derived/test_repair_2026-11-05.json`.
