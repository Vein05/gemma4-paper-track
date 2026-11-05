# Spec: BigCodeBench-Hard pilot (Gemma 4 31B's pass rate)

DRAFT 2026-10-24. Runs with the user's OK of 2026-10-24 ("sure let's pilot"). No judging. Terms follow `GLOSSARY.md`.

## Why

A second benchmark for the Quality criterion, after SWE-bench Multilingual was stopped (`spec/multilingual-replication.md`).
BigCodeBench (arXiv 2406.15877) has 1,140 Python tasks that use real libraries, each with unit tests, and its
maintainers published one program per task for many models (release v0.2.4, `sanitized_calibrated_samples.zip`). So
only Gemma's own programs need to be generated. Gemma 4 has no published BigCodeBench score. This pilot measures it on
BigCodeBench-Hard (148 tasks) and checks whether Gemma's failing programs fail for real reasons.

## Setup

- Tasks: BigCodeBench-Hard, instruct split (task described in plain English), as loaded by the `bigcodebench` package
  inside the evaluation image.
- Evaluation image: `bigcodebench/bigcodebench-evaluate:latest` from Docker Hub, pulled once as a local Apptainer file
  on the lab server; digest recorded at pull. Generation and grading both run the image's own `bigcodebench` code.
- Gemma's programs: `python3 -m bigcodebench.generate --backend openai` against Gemma 4 31B
  (`google/gemma-4-31B-it-qat-w4a16-ct`, revision `52f3f65b`) on vLLM 0.30.0 on the lab A100. Greedy (temperature 0),
  one program per task, the package's default prompt and its 1,280-token output limit, thinking off. The vLLM server is
  stopped when generation ends.
- Grading: `python3 -m bigcodebench.evaluate --execution local`, calibrated, on the server's CPUs.

## Checks

1. Reference solutions of the 148 tasks pass in our environment (`--check_gt_only`).
2. DeepSeek-V3's released Hard instruct programs regraded here: pass rate close to its published 28.4%.
3. Gemma's pass rate, and 10 of Gemma's failing programs read by hand: real bug, or failure caused by the task or
   environment.

## Next step (not part of this pilot)

If Gemma fails enough Hard or full tasks and the failures are real, a spec for the self-judging measure on BigCodeBench
(Gemma's programs and released programs of other writers, the held-out prompt adapted to programs, Gemma and outside
judges).
