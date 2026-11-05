# Spec: does Gemma trust patches that are likely under its own weights?

FROZEN 2026-11-01, before any log-probability was computed. The user's OK for the spec: 2026-11-01 ("it's fine").
Each A100 run still needs the user's OK when it starts. Status: `handoff/2026-11-01-own-patch-likelihood.md`.
Terms follow `GLOSSARY.md`. Method follows `spec/gemma-sizes-judges.md` and `spec/gemma-31b-local-judge.md`.
Background: `notes/idea-own-code-surprise-2026-10-28.md`.

## Why

The charter's open question is why Gemma 4 31B trusts its own failing patches. Wataoka et al. (2024) report that
judges favour text with low perplexity whoever wrote it, and call self-preference familiarity. Pombal et al. (2026,
Table 21) find self-preference above 1 even in the lowest whole-output perplexity quartile on LiveCodeBench. Nobody
has tested this on patches with hidden-test labels against outside judges on the same patch. This spec asks whether a
patch's likelihood under a Gemma size predicts that size's leniency, and how much of the 31B's extra trust in its own
failing patches it accounts for. It is observational: it can show that likelihood predicts leniency, not that it
causes it.

## Likelihood models

The three Gemma 4 sizes, each exactly as it was served as a judge, on the lab A100 with vLLM 0.30.0 (the environment
of all three local judge runs):

- 31B: `google/gemma-4-31B-it-qat-w4a16-ct` revision `52f3f65b` (the checkpoint that wrote the patches).
- 12B: `google/gemma-4-12B-it-qat-w4a16-ct` revision `1d2c2d7f`.
- 26B-A4B: `google/gemma-4-26B-A4B-it` revision `4d7ae498`, fp8, eager mode, CUTLASS fp8 kernel off.

One model at a time; the run does not start if more than 8 GB of GPU memory is in use.

## Patches and prompt

- The held-out patches scored by the nine paper judges, the local 31B, the 12B and the 26B-A4B (954 patches,
  runs `main-a` and `main-b`, as in `scripts/gemma_sizes_analysis.py`).
- Prompt: the judging prompt exactly (`data/judge-prompts/heldout_p1.jsonl`, system and user message, through each
  model's chat template with the generation prompt), sent with `prompt_logprobs` and 1 output token. So each patch is
  conditioned on what the judge saw: the issue and the preceding prompt text.
- Only the patch's added lines are scored (tokens whose characters lie on lines starting with `+`, not `+++`).
  Context and removed lines are the original code, not the writer's.
- Script `scripts/patch_likelihood.py` (to be written); rows in `scripts/derived/likelihood_<tag>.jsonl`: pid, added
  tokens, sum and mean log-probability, per-line means.

## Measures (fixed before any log-probability is read)

Per patch and likelihood model:

1. **Patch likelihood:** mean log-probability per token over the added lines.
2. **Least likely added line:** the lowest per-line mean among added lines with at least 3 tokens (a bug is a few
   tokens; a whole-patch mean can hide it). Secondary.
3. **Relative likelihood:** the 31B's patch likelihood minus the 26B-A4B's on the same patch, which removes code that
   any model finds predictable.

Leniency is a judge's score minus the outside judges' mean on the same patch (the paper's eight non-Gemma judges,
minus the writer's family). The 31B judge here is the local one, the same checkpoint as the likelihood model; the hosted
31B is reported beside it. Likelihoods are standardised over the 954 patches. 95% intervals: 2,000 bootstrap
resamples of issues, seed 0. Failing patches only, except where stated.

## Analyses

1. **Main test, free of the authorship confound.** Gemma's own patches were decoded at temperature 0 by the same
   checkpoint, so they are likely under it almost by construction. The main test therefore uses other writers'
   failing patches only: the slope of the 31B's leniency on patch likelihood under the 31B, with log(added + removed
   lines) as a covariate. Reported again with relative likelihood in place of patch likelihood.
2. **How much of the own-patch effect.** On all failing patches: leniency regressed on own (1 if the 31B wrote it),
   patch likelihood and log size. The own coefficient with and without patch likelihood. If fewer than 20 of the
   31B's own failing patches fall within the central 90% of other writers' failing patches on patch likelihood, this
   analysis is reported as not interpretable.
3. **Siblings.** The main test for the 12B and 26B-A4B, each with its own likelihood and leniency. Descriptive: the
   standardised difference in patch likelihood between the 31B's own patches and other writers' patches under each
   size. If the 31B's patches are about as much more likely under the 26B-A4B as under the 31B, but the 26B-A4B
   shows little extra trust in them (+3.9 [−4.1, 11.8]), familiarity alone does not explain the 31B's effect.

## Reading rule

- **Familiarity accounts for much of it:** the main test's slope has a lower bound above 0, and in analysis 2 the own
  coefficient falls by at least half when patch likelihood is added.
- **Familiarity predicts leniency but does not account for the own-patch effect:** the slope's lower bound is above 0,
  and the own coefficient falls by less than a quarter.
- **Familiarity does not predict leniency:** the slope's interval includes 0 and its upper bound is below +3 points
  per standard deviation.
- **Inconclusive:** anything else.
- The paper never writes that familiarity causes the leniency. The least likely added line is reported beside the
  main measure, never in its place.

## Development check

20 prompts with the 31B before the full run. Checks only: the scored tokens decode exactly to the added lines, no
missing values, time per prompt. No likelihood values are looked at beyond these checks.

## Predictions (written at the freeze)

- Under the 31B, its own failing patches are about 0.8 standard deviations more likely than other writers' failing
  patches; under the 26B-A4B, about 0.6.
- Main test slope about +2 points per standard deviation; lower bound above 0 with probability about 0.35.
- Analysis 2: the own coefficient falls by less than a quarter with probability about 0.55, by half or more with
  probability about 0.15. (The existing data point this way: other writers' failing patches that edit the same place
  as the 31B's are trusted as often as its own, `notes/idea-own-code-surprise-2026-10-28.md`.)

## Later

Patches written by the 12B and 26B-A4B (`spec/gemma-sizes-writers.md`) get the same three likelihoods, from this
script unchanged and on the same server. The three-way test goes in an addendum here, fixed before those patches are
judged. W&B project `gemma4-paper-track`, group `own-patch-likelihood`, logged from this Mac; changelog entry per run.
