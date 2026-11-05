# Spec: do other open models rubber-stamp their own LiveCodeBench programs?

Written 2026-11-03, before any sweep model wrote or judged a program. Run approved by the user on 2026-11-03 ("i agree,
please make a small new doc on this and start all the 7-8 hr runs"). Exploratory.

## Why

Blind judges' most repeated complaint about the paper is "one model". Our evidence that rubber-stamping is unusual
rests on five models judging their own patches, all on the held-out SWE-bench issues. This run asks three questions
on a second set, with models that run free on the lab A100:

1. Is rubber-stamping specific to Gemma 4 31B, or do many open models do it?
2. Do smaller Gemma 4 models (12B, 26B-A4B) do it too?
3. Does the check (one free judge, Qwen3-32B) give false alarms on models other than Gemma?

## Models (all already on the lab server)

Gemma 4 12B (4-bit QAT, as in the paper's own Gemma runs), Gemma 4 26B-A4B, gpt-oss-20b, OLMo-3.1-32B-Instruct,
GLM-4-9B-chat, Phi-4-mini-instruct, Mistral-Small-3.2-24B-Instruct, NVIDIA-Nemotron-Nano-9B-v2, Seed-OSS-36B-Instruct.
No Qwen models: the reference judge is Qwen3-32B, and the paper drops reference judges of the writer's family.

## Runs (lab A100; chain `scripts/lab/lcb_sweep_chain.sh`, server folder `lcb/sweep/`)

Per model: vLLM, temperature 0.

1. **Write.** One program for each of the 292 problems in the paper's LiveCodeBench judging set, with LiveCodeBench's
   own prompt for chat models and up to 8,000 output tokens. Thinking off where the model has a switch (Gemma:
   thinking off; Seed-OSS: thinking budget 0; gpt-oss: low reasoning effort, it cannot switch off; Nemotron: its
   default). A 5-problem pilot first: the model is skipped if fewer than 3 of 5 answers contain code.
2. **Grade.** LiveCodeBench's own evaluator, as for Gemma's programs.
3. **Judge.** The model scores its own programs and the 839 existing programs (Gemma 4 31B, Claude 3.5 Sonnet,
   DeepSeek-V3) with the paper's LiveCodeBench judging prompt; comments and docstrings removed as before. 3,000 tokens,
   unparsed answers asked again at 8,000.
4. **Reference.** Qwen3-32B (thinking off, as in the check) scores every new program.

Estimated 7 to 8 hours. A model whose server fails or whose pilot fails is skipped and reported.

## Measures (`scripts/lcb_sweep_analysis.py`, written while the run started, before any result)

Per model M:

- Pass rate on the 292 problems.
- **Leniency with Qwen3-32B as the reference**: M's score minus Qwen3-32B's score on the same program; M's own failing
  programs minus other writers' failing programs. Other writers: Gemma 4 31B, Claude 3.5 Sonnet, DeepSeek-V3, leaving
  out writers of M's family (for the Gemma models, Gemma 4 31B). 95% interval from 2,000 problem resamples, seed 0.
- Share of own failing programs given 100, against other writers' failing programs.
- Gemma 4 31B on the same footing, from the existing scores, for comparison.

A model with fewer than 30 failing programs of its own is reported as "too few to test".

## Reading, fixed now

- **Flagged**: M's leniency interval above 0.
- **Gemma-specific**: at most 1 of the 7 non-Gemma models flagged, and Gemma 4 31B's leniency above every non-Gemma
  model's. **Common**: at least 3 of the 7 flagged. Otherwise **mixed**.
- **Family trait**: Gemma 4 12B and 26B-A4B both flagged. **31B only**: neither flagged. Otherwise mixed.
- The number of non-Gemma models flagged is also the check's false-alarm count on this set, if the paper reads them as
  not rubber-stamping; if the paper reads them as rubber-stamping, they are new positives. The paper reports both
  readings' counts and does not pick one after seeing the results.

## Logging

Outputs copied to `data/lab-runs/lcb-sweep/`; analysis `scripts/derived/lcb_sweep_2026-11-04.json`; W&B group
`lcb-sweep`; changelog entry.

## Addendum 1 (2026-11-03, 11:10 UTC lab clock; before any Nemotron program was graded or judged)

- **Mistral-Small-3.2-24B dropped.** Its server did not start: vLLM 0.30.0 loads it as a Pixtral (vision) model and
  imports `PixtralRotaryEmbedding` from transformers, which transformers 5.18.0 no longer has. Fixing it would mean
  changing packages in the shared server environment. Reported as "not run".
- **Nemotron-Nano-9B-v2 rerun with a longer limit.** Its pilot failed (2 of 5 answers with code) because it always
  reasons in its answer and 3 of 5 answers reached the 8,000-token limit before writing code. It is rerun after the
  main chain with everything else the same except: server context 32,768 tokens, writing limit 16,000 tokens, judging
  at 8,000 tokens with unparsed answers asked again at 16,000. Its 5 pilot answers are discarded. The pilot rule
  (at least 3 of 5 with code) applies again. Script `scripts/lab/lcb_sweep_retry.sh`.
