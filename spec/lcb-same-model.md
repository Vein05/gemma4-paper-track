# Spec: do gpt-oss-120b and Llama-4-Maverick favor their own contest programs under our measure?

Written 2026-11-05, before either model wrote or judged a program for this test. Run approved by the user on 2026-11-05
("sure add them"). Exploratory: chosen after reading both results it compares.

## Why

Pombal et al. (2026, Table 1) report that on LiveCodeBench gpt-oss-120b wrongly passes unit tests of its own programs
5.97 times as often as those of unrelated models, and Llama 4 Maverick 1.34 times as often. On our held-out SWE-bench
Verified issues, neither model shows leniency on its own failing patches: gpt-oss-120b +2.9 [-3.3, 8.8],
Llama-4-Maverick +2.8 [-5.0, 10.8]. Task and measure both differ between the two results. This test keeps the model
and our measure and changes only the task, to contest programs. It does not vary the measure on repository patches.

## Runs (OpenRouter from this Mac; grading on the lab server's CPUs, no GPU)

1. **Prompts.** LiveCodeBench's own chat prompt for the 292 problems in `data/livecodebench-pilot/judging/sweep_ids.json`,
   the same problems as the model sweep (`spec/lcb-model-sweep.md`). Half were chosen because Gemma 4 31B fails them.
2. **Write.** `openai/gpt-oss-120b` and `meta-llama/llama-4-maverick`, one program per problem, temperature 0, 8,000 output
   tokens. gpt-oss-120b always reasons, so it runs at low effort with 3,000 more tokens, as it did when judging. Maverick
   runs with reasoning off. Pilot of 5 problems per model, read for infrastructure only: a model with fewer than 3 of 5
   answers containing code is reported as not run.
3. **Grade.** LiveCodeBench's own evaluator at commit `28fef95e`, in the container used for the sweep.
4. **Judge.** The paper's LiveCodeBench judging prompt, comments and docstrings removed. 3,000 tokens; unparsed answers
   are asked again at 8,000. Each model judges its own new programs. Its outside judges score them too:
   - gpt-oss-120b's programs: gpt-oss-120b, Gemma 4 31B, Qwen3.5-9B, GLM-4.7-Flash, Llama-4-Maverick.
   - Llama-4-Maverick's programs: Llama-4-Maverick, Gemma 4 31B, gpt-oss-20b, Qwen3.5-9B, GLM-4.7-Flash, gpt-oss-120b.
   Both models already scored the existing programs of Gemma 4 31B, Claude 3.5 Sonnet and DeepSeek-V3
   (`scripts/derived/lcb_<judge>.jsonl`).

Qwen3-32B does not score the new programs, because that needs the A100, so these two models do not join Figure 2.

## Budget

Estimated from the token counts and prices of the existing LiveCodeBench judging: writing about $0.60, judging about
$0.90, about $1.50 in all. Hard stop at $3.00 of recorded spending. OpenRouter credit at the start: $7.22.

## Measure (`scripts/lcb_same_model.py analyze`, written before any program exists)

The definition of the held-out result in `scripts/other_models_leniency.py`. On each program, the model's score minus the
mean score of its outside judges, leaving out a judge of the program writer's family. The result is the mean on the
model's own failing programs minus the mean on the failing programs of Gemma 4 31B, Claude 3.5 Sonnet and DeepSeek-V3.
95% interval from 2,000 problem resamples, seed 0. Also reported: pass rate, mean raw score on own and other failing
programs, share scored 100, and the number of programs lost to empty answers or missing scores.

Check of the code: run on Gemma 4 31B, it must return the paper's +23.0 and its interval from
`scripts/derived/lcb_judging_2026-11-01.json`. If it does not, no result is read until the difference is explained.

## Reading, fixed now

Per model:

- **Too few to test:** fewer than 30 failing programs of its own.
- **Lenient:** the interval lies above 0, and its mean raw score on its own failing programs is above its mean on other
  writers' failing programs. The raw-score condition is the guard the sweep showed is needed for Phi-4-mini.
- **Reference artefact:** the interval lies above 0, and the raw-score condition fails.
- **Not lenient:** the interval includes 0 or lies below it.

For the paper:

- **Both lenient:** these two models favor their own contest programs under our measure, and we detect no such
  leniency on their repository patches. The measure alone therefore does not explain the difference from Pombal et
  al.; the task may. Agent use and the patch format change with the task, so we do not name one cause.
- **Neither lenient:** our whole-program measure does not show on contest programs what their unit-test measure shows.
  The measure may explain the difference, and we have no evidence that the task does.
- **Anything else:** each model is reported by name, with no statement about task or measure.

The result replaces the sentence "The task or the measure could explain this." in Section 4 and gets a table in the
supplement. It is reported whichever way it falls. No other model, setting or problem set is tried after reading it.

## Limits fixed now

Problem selection follows Gemma 4 31B's failures. Pombal et al. use a later split of LiveCodeBench and unit-test verdicts,
so this does not repeat their experiment. Hosted providers vary between calls, and each row records its provider.

## Logging

Outputs in `data/lab-runs/lcb-same-model/`; analysis `scripts/derived/lcb_same_model_2026-11-05.json`; W&B group
`lcb-same-model`; changelog entry with spending. No GPU, so no compute-ledger entry.
