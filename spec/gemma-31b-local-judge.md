# Spec: Gemma 4 31B as judge, served locally from the competition checkpoint

FROZEN 2026-10-28, before any score from the local judge (the smoke test had not run). The user's OK for the smoke test
and the full judging: 2026-10-28 ("let's run this?"). Terms follow `GLOSSARY.md`. Method, measures and reading rule
follow `spec/gemma-sizes-judges.md`.

## Why

In the paper, Gemma 4 31B as judge is the hosted model. OpenRouter sent its calls to nine providers, most of them
serving 4-bit or 8-bit weights, and the precision of each call was not recorded (`changelog/2026-10-28.md`). The
patches were written by the 4-bit competition checkpoint, run locally with vLLM. This run asks whether the
rubber-stamping holds when the judge is that same checkpoint, served locally, as an agent in the competition would run
it. It also removes one difference between 31B and the Gemma 4 12B and 26B-A4B judges, which were served locally on the
same GPU. It says nothing about why Gemma trusts its own failing patches.

## Judge

`google/gemma-4-31B-it-qat-w4a16-ct` revision `52f3f65b`, the checkpoint that wrote Gemma's held-out patches. Served on
the lab A100 with vLLM 0.30.0, the environment of the 12B judge (the agent runs used vLLM 0.31.0 on an L40S). Same
flags as the 12B judge: context 32,768, 16 sequences, prefix caching, the gemma4 reasoning parser, no tool parser;
temperature 0, thinking off. Served model name and tag `gemma4-31b-local`.

## Patches, prompt and parser

As in `spec/gemma-sizes-judges.md`: the 1,063 held-out prompts in `data/judge-prompts/heldout_p1.jsonl` (md5
`5356d2e9…6b29`), run by `scripts/local_judging.py` (md5 `ab3f1c21…a164`) with 3,000 output tokens and one re-ask of
unparsed answers with 8,000. Rows in `scripts/derived/fresh_gemma4-31b-local.jsonl`, `provider` `local-vllm`.

## Measures (fixed before any score)

On the held-out patches scored by the paper's nine judges and the local judge, with the eight outside judges as in the
paper, for the local judge beside the hosted 31B judge:

1. Share of 31B's own failing patches scored 100, beside the share of other writers' failing patches scored 100.
2. Leniency on 31B's failing patches minus leniency on other writers' failing patches, 95% interval from 2,000
   bootstrap resamples of issues.
3. The same difference on passing patches.
4. AUROC on 31B's patches and on other writers' patches.
5. Paired: the hosted judge's measure 2 minus the local judge's measure 2, with its interval.

## Smoke test

20 prompts (`local_judging.py run --smoke`: 10 of Gemma's patches, 10 of other writers'). Checks: the server starts in
the memory free on the shared GPU, answers parse, no thinking tokens, time per call.

## Analysis

`scripts/gemma_sizes_analysis.py --sizes gemma4-31b-local` (sha256 `510c1185…a9a3`, unchanged), on the runs `main-a`
and `main-b`. A patch enters only if all nine paper judges and the local judge scored it. If the local judge drops
patches, the hosted judge is reported on the smaller set (the script does this).

## Reading rule

- Validity first: at least 95% of prompts parse after the one re-ask, no answer carries thinking tokens, and the AUROC
  on other writers' patches is at least 0.60. A run that fails this is reported as invalid, in the supplement only.
- **Holds with the local judge:** measure 2 has a 95% interval with lower bound above 0.
- **Does not hold:** the interval includes 0 and its upper bound is below +8.3, half of the hosted judge's +16.6.
- **Inconclusive:** anything else.
- **Hosted and local differ:** measure 5 has an interval that excludes 0; the direction is reported. Otherwise the
  paper says no difference was detected, not that the two are the same.
- The share scored 100 (measure 1) is reported beside measure 2, never alone.

## Predictions (written at the freeze, before any score)

- Gives 100 to about 60% of 31B's failing patches and about 35% of other writers' failing patches.
- Measure 2 about +15 points, interval about ±7; lower bound above 0 with probability about 0.85.
- Measure 5 interval includes 0 with probability about 0.8.
- AUROC about 0.62 on 31B's patches and 0.75 on other writers'. Fails the validity check with probability about 0.05.
