# Spec: Gemma 4 31B on the full BigCodeBench (complete split)

Written 2026-10-23 (US Central), before the run. Runs with the user's OK of 2026-10-23 ("let's run it it's fine").
No judging. Follows the BigCodeBench-Hard pilot (`spec/bigcodebench-pilot.md`, results in
`data/bigcodebench-pilot/`). Terms follow `GLOSSARY.md`.

## Why

The pilot found Gemma passes 41 of 148 BigCodeBench-Hard tasks, but only 2 of 10 failing programs read by hand were
real bugs (`data/bigcodebench-pilot/hand-check.md`). The other 8 failed tests that check how the code is written
(fakes of `open`, `Popen`, `os.path.exists`), or missed requirements that the short instructions leave out or that no
prompt states. A self-judging measure on BigCodeBench needs failing programs that are really wrong. This run gives
Gemma the full task descriptions (complete split: signature plus the original docstring with its examples) on all
1,140 tasks, so that enough failures are left after the filters below.

## Setup

- Tasks: BigCodeBench v0.1.4, all 1,140 tasks, complete split, as loaded by the `bigcodebench` package 0.2.4 inside the
  pilot's evaluation image (`bcb/bigcodebench-evaluate.sif`, digest `sha256:a3cd34ec…cd405`).
- Gemma's programs: as in the pilot (`bigcodebench.generate --backend openai`, greedy, the package's prompt and its
  1,280-token limit, thinking off), against Gemma 4 31B (`google/gemma-4-31B-it-qat-w4a16-ct`, revision `52f3f65b`) on
  vLLM 0.30.0 on the lab A100, in 8 shards at once (the server takes 8 requests at a time). The dataset is loaded once
  before the shards start, because two shards that started together in the pilot raced on its download. The vLLM
  server is stopped when generation ends.
- Grading: `bigcodebench.evaluate --execution local --parallel 16`, calibrated, on the server's CPUs, as in the pilot.
- Commands: `scripts/lab/bcb_pilot.sh full-validate | full-generate | full-grade`.

## Checks

1. Reference solutions pass in our environment (the evaluate run reports this for all 1,140 tasks).
2. DeepSeek-V3's released full complete programs (release v0.2.4, `sanitized_calibrated_samples.zip`) regraded here:
   pass rate close to its published 62.2%.
3. Gemma's pass rate on all 1,140 tasks.

## Filters and the gate before any judging

- Tests that use fakes: a task is dropped when its test code contains `patch(`, `MagicMock`, `mock_open` or `Mock(`
  (the pilot's definition). Tasks whose reference solution fails here are dropped too.
- Gate: 20 of Gemma's failing programs on the kept tasks, sampled with `random.seed(0)`, are read with the pilot's
  four verdicts (real bug; test checks the implementation; requirement only in the full description; requirement
  stated nowhere). A judging spec is written only if most of the 20 are real bugs. A person checks at least part of the
  sample before any claim goes into the paper.

## Predictions (written before the run, from the chat of 2026-10-23)

- Gemma's pass rate about 58% (52 to 64%): DeepSeek-V3 scores 62.2% on this split and tied Gemma on Hard instruct in
  our regrade.
- About 480 failing programs, about 330 after the fakes filter.
- About half of the filtered failures are real bugs (30 to 70%). Chance that the gate passes: about 55%.

## Next step (not part of this run)

If the gate passes: a judging spec (Gemma's programs and released programs of other writers, regraded here; the
held-out prompt adapted to programs; Gemma and outside judges). It needs an OpenRouter top-up and the user's OK.
