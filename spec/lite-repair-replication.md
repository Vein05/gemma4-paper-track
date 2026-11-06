# Spec: does the gate and repair work on Gemma patches written by another team?

Written 2026-11-06, before the gate or any repair ran on these patches. The user approved the GPU run the same day. The
gate is `spec/existing-test-gate.md` and the repair is `spec/test-repair.md`, unchanged. Terms follow `GLOSSARY.md`.

## Why

The repair result (14 of 26 blocked failing patches pass with the failing tests shown, against 6 with a second look;
the sign test had 8 issues against 0) comes from one run per patch on issues we had inspected many times. This repeats it
on issues the gate and repair have never seen, on patches another team wrote.

## Patches (rule fixed now, no labels used)

Gemma 4 31B's patches from `data/public/third-party-lite/patches.jsonl` (another team's run, `spec/third-party-lite.md`:
full weights, thinking on, mini-SWE-agent 2.2.1) on the 263 SWE-bench Lite issues outside the paper's 193 held-out
issues. List: `data/lite-repair/issues.txt`. Plus each issue's reference patch, as a passing control for the gate.

The patches differ from the held-out ones in three ways: another model file, thinking on and another agent version. The
repairing agent is still the 4-bit Gemma with thinking off, as in `spec/test-repair.md`, so this asks whether the repair
works on patches it did not write in the same run.

## Gate and repair

Same code and limits. `scripts/existing_test_gate.py` and `scripts/test_repair.py` read the dataset name from
`SWE_DATASET` (default Verified) and nothing else changes. Every Gemma patch the gate blocks gets both arms, failing
tests shown and second look: mini-SWE-agent 1.7.0, step limit 50, context 65,536, temperature 0, thinking off, the
`testbed` environment active, one run per patch. vLLM gets 0.70 of the GPU's memory, which changes speed only.

## Labels

Repaired patches are graded with `scripts/eval_apptainer.py` against `princeton-nlp/SWE-bench_Lite`. A repair count needs
the same grader before and after, so the start patch and the reference patch of every blocked issue are graded the same
way, before any repair label is read. "Failing" and "passing" below mean our grade of the start patch. An issue whose
reference patch fails with our grader is left out. Agreement with the other team's labels is reported.

## Measures and reading rules (the reading rules of `spec/test-repair.md`)

Analysis: `scripts/lite_repair.py analyze`.

1. **Primary.** Among blocked failing patches, passes after repair with the failing tests shown against a second look;
   exact one-sided sign test on discordant issues.
   - **The failing tests help repair:** more pass with the tests shown, p < 0.05.
   - **A second look is enough:** p ≥ 0.05 and the second look repairs at least as many.
   - **No repair:** fewer than 3 pass with the tests shown.
   - Otherwise (more repairs with the tests shown, p ≥ 0.05): counts only, no credit to the test output.
2. Harm: blocked passing patches that fail after repair, per arm.
3. End to end: of the failing patches Gemma scored 100 by the other team's labels and our earlier scores
   (`scripts/derived/lite_gemma4-31b.jsonl`), how many the gate blocks and how many pass after repair; of the correct
   patches Gemma scored 100, how many the gate blocks and how many are broken by repair.
4. Gate: blocks on failing and passing patches and on reference patches, and coverage.
5. Cost: GPU-hours, calls and tokens.

A run that does not submit keeps the start patch and its grade.

## Predictions, written before the run (judgment, not evidence)

- More repairs with the tests shown than with a second look: 80 to 85% likely. Sign test p < 0.05: about 60%.
- More patches fixed than broken among those Gemma scored 100: about 70%.
- At least 54% of blocked failing patches repaired, the held-out rate: about 15%. Point guess about 35% (13 of 38)
  with the tests shown, 15 to 20% with a second look.
- At least 17% of failing patches scored 100 repaired, the held-out rate: about 20%. Point guess about 10%.
- 3 to 5 of 126 correct patches scored 100 broken. About 38 failing and 13 passing patches blocked.

## Run and logging

CPU gate `scripts/lab/lite_gate_repair.sh`, then GPU chain `scripts/lab/test_repair_chain.sh`, after the non-Python run
has released the GPU. One seed tonight. Further seeds need temperature above 0 and a separate spec. W&B group
`lite-repair`, logged from the Mac; changelog with start, end and GPU-hours; compute ledger updated; outputs in
`data/lab-runs/lite-repair/`.
