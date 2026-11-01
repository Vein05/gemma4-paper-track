# Spec: Gemma 4 31B on LiveCodeBench (pass rate and whether its failures are real bugs)

Written 2026-11-01, before any Gemma call on this data. Runs with the user's OK of 2026-11-01 ("let's pull that in
server thanks!! livecode bench and such and see how does gemma does in it"). No judging. Terms follow `GLOSSARY.md`.

## Why

A second benchmark for the Quality criterion. SWE-bench Multilingual stopped (Gemma looped under tool calling, about
10 issues an hour); BigCodeBench failed its gate (5 of 20 failing programs were real bugs; the rest failed on
unstated requirements, tests of the implementation or prompts with two readings). LiveCodeBench problems come from
contests (AtCoder, LeetCode, Codeforces) with exact input and output, so a failing program should be a wrong program.
Its maintainers released ten programs per problem with grades for about 70 models (`LiveCodeBench/submissions`,
last commit 2025-08-01), so only Gemma's programs need generating. Pombal et al. (2026) found no self-preference in
Gemma 3 on LiveCodeBench.

## Setup

- Problems: release_v6 of `livecodebench/code_generation_lite` (Hugging Face), the 1,055 problems dated 2023-05-07
  to 2025-04-06 that the released submission files cover. Revision recorded at download.
- Gemma's programs: Gemma 4 31B (`google/gemma-4-31B-it-qat-w4a16-ct`, the checkpoint of the paper's own runs) on vLLM
  on the lab A100, temperature 0, one program per problem, thinking off, LiveCodeBench's own prompt for chat models
  (`lcb_runner` prompt code) and its default output limit. The vLLM server is stopped when generation ends.
- Grading: `lcb_runner`'s own evaluator (the custom-output path), run inside an Apptainer container that sees only
  the work folder, on the server's CPUs.

## Checks

1. Environment: DeepSeek-V3's released programs (first of its ten per problem) regraded here. Pass rate close to the
   released grades of the same programs (49.8%).
2. Gemma's pass rate overall and by difficulty.
3. 20 of Gemma's failing programs (`random.seed(0)`) read against the problem and the failing test: real bug
   (wrong answer, wrong algorithm, too slow for the stated limits), or failure from the task or the environment.

## Gate for a judging spec

Most of the 20 (at least 11) are real bugs, and Gemma fails at least 150 problems. Otherwise, no judging on
LiveCodeBench.

## Predictions (before the run)

- Gemma passes 40-55% (DeepSeek-V3's released first programs: 49.8%).
- At least 16 of the 20 failing programs are real bugs.

## Not part of this run

Judging (own vs other writers' programs, Gemma and outside judges) needs its own spec after the gate.

## Addendum, 2026-11-01: rerun of the cut-off answers with an 8,000-token limit

Written after the first run and before the rerun, with the user's OK ("icnrease it to around 8k and then let's see!").

- Why: 133 of Gemma's 1,055 answers (118 of them hard problems) reached the 2,000-token output limit before the code
  block closed, so they have no program. These are failures of the output limit, not of the program, and they would
  fill the hand check with non-bugs.
- Change: only those 133 problems are generated again, with everything else the same (same server, prompt,
  temperature 0, thinking off) and a limit of 8,000 output tokens (`gemma4-31b-8k.jsonl`). The other 922 answers stay
  as they are. Their rows replace the cut-off ones and all 1,055 are graded again (`gemma4-31b-merged.json`).
- The pass rate at 2,000 tokens (78.5%) stays the result under LiveCodeBench's default setup. The merged one is
  reported as the result with the 8,000-token limit for the cut-off answers.
- Hand check and gate: as above, with the 20 failing programs drawn (`random.seed(0)`) from the merged run's
  failures. Answers still cut off at 8,000 tokens are counted and reported, and left out of the draw.
- Predictions (before the rerun): at most 30 of the 133 are still cut off at 8,000 tokens; 30-60% of the 133 pass.
